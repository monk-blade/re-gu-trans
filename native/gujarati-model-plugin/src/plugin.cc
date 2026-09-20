#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <memory>
#include <mutex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

#include <onnxruntime_cxx_api.h>

#if defined(_WIN32)
#define AKSHAR_EXPORT extern "C" __declspec(dllexport)
#else
#define AKSHAR_EXPORT extern "C" __attribute__((visibility("default")))
#endif

namespace {
constexpr const char* kVersion = "indicxlit-fairseq-v1.0";
constexpr const char* kLongIMatra = "\xE0\xAB\x80";
constexpr const char* kShortIMatra = "\xE0\xAA\xBF";
constexpr double kOrthographicVariantPenalty = 0.5;
constexpr int kMaxDecodeSteps = 32;
constexpr int kDefaultBeamWidth = 8;

bool validRomanWord(const std::string& roman) {
  if (roman.empty() || roman.size() > 32) return false;
  bool previousSeparator = false;
  for (size_t index = 0; index < roman.size(); ++index) {
    const unsigned char ch = static_cast<unsigned char>(roman[index]);
    const bool letter = (ch >= 'a' && ch <= 'z') || (ch >= 'A' && ch <= 'Z');
    const bool separator = ch == '+' || ch == '\'' || ch == '-';
    if (!letter && !separator) return false;
    if (separator && (index == 0 || index + 1 == roman.size() || previousSeparator)) return false;
    previousSeparator = separator;
  }
  return true;
}

std::vector<uint32_t> utf8Codepoints(const std::string& text) {
  std::vector<uint32_t> output;
  for (size_t index = 0; index < text.size();) {
    const unsigned char first = static_cast<unsigned char>(text[index]);
    uint32_t value = 0;
    size_t length = 0;
    if (first < 0x80) {
      value = first;
      length = 1;
    } else if ((first & 0xE0) == 0xC0) {
      value = first & 0x1F;
      length = 2;
    } else if ((first & 0xF0) == 0xE0) {
      value = first & 0x0F;
      length = 3;
    } else if ((first & 0xF8) == 0xF0) {
      value = first & 0x07;
      length = 4;
    } else {
      return {};
    }
    if (index + length > text.size()) return {};
    for (size_t offset = 1; offset < length; ++offset) {
      const unsigned char next = static_cast<unsigned char>(text[index + offset]);
      if ((next & 0xC0) != 0x80) return {};
      value = (value << 6) | (next & 0x3F);
    }
    output.push_back(value);
    index += length;
  }
  return output;
}

bool validGujaratiWord(const std::string& text) {
  const auto chars = utf8Codepoints(text);
  if (chars.empty()) return false;
  if (chars.size() == 1 && chars[0] == 0x0AD0) return true;
  bool haveBase = false;
  bool consonant = false;
  bool matra = false;
  bool modifier = false;
  bool afterVirama = false;
  bool afterJoiner = false;
  bool afterNukta = false;
  for (uint32_t ch : chars) {
    const bool independent = ch >= 0x0A85 && ch <= 0x0A94;
    const bool isConsonant = (ch >= 0x0A95 && ch <= 0x0AB9) || ch == 0x0AF9;
    const bool isMatra = (ch >= 0x0ABE && ch <= 0x0ACC) ||
                         (ch >= 0x0AE2 && ch <= 0x0AE3);
    const bool isModifier = ch >= 0x0A81 && ch <= 0x0A83;
    if (independent || isConsonant) {
      if ((afterVirama || afterJoiner) && !isConsonant) return false;
      haveBase = true;
      consonant = isConsonant;
      matra = modifier = afterVirama = afterJoiner = afterNukta = false;
    } else if (ch == 0x0ABC) {
      if (!haveBase || !consonant || matra || modifier || afterVirama || afterNukta) return false;
      afterNukta = true;
    } else if (ch == 0x0ACD) {
      if (!haveBase || !consonant || matra || modifier || afterVirama) return false;
      afterVirama = true;
      afterJoiner = false;
    } else if (ch == 0x200C || ch == 0x200D) {
      if (!afterVirama || afterJoiner) return false;
      afterJoiner = true;
    } else if (isMatra) {
      if (!haveBase || !consonant || matra || modifier || afterVirama || afterJoiner) return false;
      matra = true;
    } else if (isModifier) {
      if (!haveBase || modifier || afterVirama || afterJoiner) return false;
      modifier = true;
    } else {
      return false;
    }
  }
  return haveBase && !afterVirama && !afterJoiner;
}

void addOrthographicVariants(const std::string& native, double score,
                             std::unordered_map<std::string, double>* unique) {
  size_t offset = 0;
  while ((offset = native.find(kLongIMatra, offset)) != std::string::npos) {
    std::string variant = native;
    variant.replace(offset, 3, kShortIMatra);
    if (validGujaratiWord(variant)) {
      auto found = unique->find(variant);
      if (found == unique->end() || score - kOrthographicVariantPenalty > found->second) {
        (*unique)[variant] = score - kOrthographicVariantPenalty;
      }
    }
    offset += 3;
  }
}

std::string jsonEscape(const std::string& value) {
  std::string output;
  output.reserve(value.size() + 8);
  for (unsigned char ch : value) {
    if (ch == '"' || ch == '\\') {
      output.push_back('\\');
      output.push_back(static_cast<char>(ch));
    } else if (ch < 0x20) {
      const char* hex = "0123456789abcdef";
      output += "\\u00";
      output.push_back(hex[ch >> 4]);
      output.push_back(hex[ch & 15]);
    } else {
      output.push_back(static_cast<char>(ch));
    }
  }
  return output;
}

// Minimal recursive-descent reader for the fixed shape written by
// scripts/export/export_indicxlit_onnx.py:
//   {"src": [...strings], "tgt": [...strings],
//    "special_tokens": {"bos":N,"pad":N,"eos":N,"unk":N}, ...other string fields}
// Not a general-purpose JSON parser; only handles what that writer produces.
class VocabJsonReader {
 public:
  struct Vocab {
    std::vector<std::string> src;
    std::vector<std::string> tgt;
    std::unordered_map<std::string, int64_t> specialTokens;
  };

  static Vocab parse(const std::string& text) {
    VocabJsonReader reader(text);
    return reader.parseObject();
  }

 private:
  explicit VocabJsonReader(const std::string& text) : text_(text), pos_(0) {}

  char peek() const { return pos_ < text_.size() ? text_[pos_] : '\0'; }

  void expect(char c) {
    if (peek() != c) throw std::runtime_error("vocab.json: malformed document");
    ++pos_;
  }

  void skipWs() {
    while (pos_ < text_.size() && std::isspace(static_cast<unsigned char>(text_[pos_]))) ++pos_;
  }

  static void appendUtf8(std::string* out, unsigned int code) {
    if (code < 0x80) {
      out->push_back(static_cast<char>(code));
    } else if (code < 0x800) {
      out->push_back(static_cast<char>(0xC0 | (code >> 6)));
      out->push_back(static_cast<char>(0x80 | (code & 0x3F)));
    } else {
      out->push_back(static_cast<char>(0xE0 | (code >> 12)));
      out->push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
      out->push_back(static_cast<char>(0x80 | (code & 0x3F)));
    }
  }

  std::string parseString() {
    expect('"');
    std::string out;
    while (peek() != '"') {
      if (pos_ >= text_.size()) throw std::runtime_error("vocab.json: unterminated string");
      const char c = text_[pos_++];
      if (c != '\\') {
        out.push_back(c);
        continue;
      }
      if (pos_ >= text_.size()) throw std::runtime_error("vocab.json: bad escape");
      const char esc = text_[pos_++];
      switch (esc) {
        case '"': out.push_back('"'); break;
        case '\\': out.push_back('\\'); break;
        case '/': out.push_back('/'); break;
        case 'n': out.push_back('\n'); break;
        case 't': out.push_back('\t'); break;
        case 'r': out.push_back('\r'); break;
        case 'u': {
          if (pos_ + 4 > text_.size()) throw std::runtime_error("vocab.json: bad unicode escape");
          const unsigned int code = static_cast<unsigned int>(
              std::stoul(text_.substr(pos_, 4), nullptr, 16));
          pos_ += 4;
          appendUtf8(&out, code);
          break;
        }
        default: out.push_back(esc); break;
      }
    }
    ++pos_;  // closing quote
    return out;
  }

  std::vector<std::string> parseStringArray() {
    std::vector<std::string> out;
    expect('[');
    skipWs();
    if (peek() == ']') {
      ++pos_;
      return out;
    }
    while (true) {
      skipWs();
      out.push_back(parseString());
      skipWs();
      if (peek() == ',') {
        ++pos_;
        continue;
      }
      expect(']');
      break;
    }
    return out;
  }

  std::unordered_map<std::string, int64_t> parseIntObject() {
    std::unordered_map<std::string, int64_t> out;
    expect('{');
    skipWs();
    if (peek() == '}') {
      ++pos_;
      return out;
    }
    while (true) {
      skipWs();
      const std::string key = parseString();
      skipWs();
      expect(':');
      skipWs();
      const size_t start = pos_;
      if (peek() == '-') ++pos_;
      while (pos_ < text_.size() && std::isdigit(static_cast<unsigned char>(text_[pos_]))) ++pos_;
      out[key] = std::stoll(text_.substr(start, pos_ - start));
      skipWs();
      if (peek() == ',') {
        ++pos_;
        continue;
      }
      expect('}');
      break;
    }
    return out;
  }

  void skipValue() {
    skipWs();
    if (peek() == '"') {
      parseString();
      return;
    }
    if (peek() == '[') {
      parseStringArray();
      return;
    }
    if (peek() == '{') {
      parseIntObject();
      return;
    }
    while (pos_ < text_.size() && text_[pos_] != ',' && text_[pos_] != '}') ++pos_;
  }

  Vocab parseObject() {
    Vocab vocab;
    skipWs();
    expect('{');
    skipWs();
    if (peek() == '}') {
      ++pos_;
      return vocab;
    }
    while (true) {
      skipWs();
      const std::string key = parseString();
      skipWs();
      expect(':');
      skipWs();
      if (key == "src") {
        vocab.src = parseStringArray();
      } else if (key == "tgt") {
        vocab.tgt = parseStringArray();
      } else if (key == "special_tokens") {
        vocab.specialTokens = parseIntObject();
      } else {
        skipValue();
      }
      skipWs();
      if (peek() == ',') {
        ++pos_;
        continue;
      }
      expect('}');
      break;
    }
    return vocab;
  }

  const std::string& text_;
  size_t pos_;
};

struct Beam {
  double score;
  std::vector<int64_t> tokens;
};

// Seq2seq (encoder+decoder, autoregressive beam search) inference for the
// AI4Bharat IndicXlit checkpoint, exported to ONNX by
// scripts/export/export_indicxlit_onnx.py. Unlike the single-pass CTC model
// this replaces, every candidate requires up to kMaxDecodeSteps sequential
// decoder calls.
class Model {
 public:
  explicit Model(const std::string& root)
      : env_(ORT_LOGGING_LEVEL_WARNING, "akshar-gu"), options_(), encoder_(nullptr), decoder_(nullptr) {
    options_.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
    options_.SetIntraOpNumThreads(1);
    loadVocabulary(root + "/vocab.json");
#if defined(_WIN32)
    std::wstring rootWide(root.begin(), root.end());
    encoder_ = Ort::Session(env_, (rootWide + L"\\indicxlit_encoder.onnx").c_str(), options_);
    decoder_ = Ort::Session(env_, (rootWide + L"\\indicxlit_decoder_v2.onnx").c_str(), options_);
#else
    encoder_ = Ort::Session(env_, (root + "/indicxlit_encoder.onnx").c_str(), options_);
    decoder_ = Ort::Session(env_, (root + "/indicxlit_decoder_v2.onnx").c_str(), options_);
#endif
  }

  std::string nbest(const std::string& roman, int requested) {
    if (!validRomanWord(roman)) return "[]";
    const int count = std::max(1, std::min(8, requested));
    const int beamWidth = std::max(count, std::min(12, kDefaultBeamWidth));

    auto memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

    std::vector<int64_t> srcIds;
    srcIds.reserve(roman.size() + 2);
    srcIds.push_back(langTokenId_);
    for (unsigned char ch : roman) {
      const std::string key(1, static_cast<char>(std::tolower(ch)));
      const auto found = srcIndex_.find(key);
      srcIds.push_back(found == srcIndex_.end() ? unk_ : found->second);
    }
    srcIds.push_back(eos_);

    int64_t srcLenOut = 0;
    int64_t hidden = 0;
    std::vector<float> encoderOut;
    {
      std::vector<int64_t> srcShape{1, static_cast<int64_t>(srcIds.size())};
      auto srcTensor = Ort::Value::CreateTensor<int64_t>(
          memory, srcIds.data(), srcIds.size(), srcShape.data(), srcShape.size());
      const char* inputNames[] = {"src_tokens"};
      const char* outputNames[] = {"encoder_out"};
      auto outputs = encoder_.Run(Ort::RunOptions{nullptr}, inputNames, &srcTensor, 1, outputNames, 1);
      const auto shape = outputs[0].GetTensorTypeAndShapeInfo().GetShape();
      if (shape.size() != 3 || shape[1] != 1) throw std::runtime_error("invalid encoder_out shape");
      srcLenOut = shape[0];
      hidden = shape[2];
      const float* data = outputs[0].GetTensorData<float>();
      encoderOut.assign(data, data + static_cast<size_t>(srcLenOut) * static_cast<size_t>(hidden));
    }

    std::vector<Beam> beams{{0.0, {eos_}}};
    std::vector<Beam> finished;
    for (int step = 0; step < kMaxDecodeSteps && !beams.empty(); ++step) {
      const size_t numBeams = beams.size();
      const size_t curLen = beams[0].tokens.size();

      std::vector<int64_t> prevFlat(numBeams * curLen);
      for (size_t b = 0; b < numBeams; ++b) {
        std::copy(beams[b].tokens.begin(), beams[b].tokens.end(), prevFlat.begin() + b * curLen);
      }
      std::vector<int64_t> prevShape{static_cast<int64_t>(numBeams), static_cast<int64_t>(curLen)};
      auto prevTensor = Ort::Value::CreateTensor<int64_t>(
          memory, prevFlat.data(), prevFlat.size(), prevShape.data(), prevShape.size());

      std::vector<float> encRepeat(static_cast<size_t>(srcLenOut) * numBeams * static_cast<size_t>(hidden));
      for (int64_t t = 0; t < srcLenOut; ++t) {
        const float* src = encoderOut.data() + static_cast<size_t>(t) * static_cast<size_t>(hidden);
        for (size_t b = 0; b < numBeams; ++b) {
          float* dst = encRepeat.data() + (static_cast<size_t>(t) * numBeams + b) * static_cast<size_t>(hidden);
          std::copy(src, src + hidden, dst);
        }
      }
      std::vector<int64_t> encShape{srcLenOut, static_cast<int64_t>(numBeams), hidden};
      auto encTensor = Ort::Value::CreateTensor<float>(
          memory, encRepeat.data(), encRepeat.size(), encShape.data(), encShape.size());

      const char* inputNames[] = {"prev_tokens", "encoder_out"};
      const char* outputNames[] = {"logits"};
      Ort::Value inputs[2] = {std::move(prevTensor), std::move(encTensor)};
      auto outputs = decoder_.Run(Ort::RunOptions{nullptr}, inputNames, inputs, 2, outputNames, 1);
      const auto logitsShape = outputs[0].GetTensorTypeAndShapeInfo().GetShape();
      if (logitsShape.size() != 3 || static_cast<size_t>(logitsShape[0]) != numBeams) {
        throw std::runtime_error("invalid decoder logits shape");
      }
      const int64_t vocabSize = logitsShape[2];
      const float* logits = outputs[0].GetTensorData<float>();

      std::vector<Beam> expanded;
      expanded.reserve(numBeams * static_cast<size_t>(beamWidth) * 2);
      for (size_t b = 0; b < numBeams; ++b) {
        const float* row = logits + (b * curLen + (curLen - 1)) * static_cast<size_t>(vocabSize);
        const float maximum = *std::max_element(row, row + vocabSize);
        double sum = 0.0;
        for (int64_t v = 0; v < vocabSize; ++v) sum += std::exp(static_cast<double>(row[v]) - maximum);
        const double normalizer = static_cast<double>(maximum) + std::log(sum);

        std::vector<int64_t> indices(static_cast<size_t>(vocabSize));
        for (int64_t v = 0; v < vocabSize; ++v) indices[static_cast<size_t>(v)] = v;
        const size_t keep = std::min(static_cast<size_t>(beamWidth * 2), indices.size());
        std::partial_sort(indices.begin(), indices.begin() + keep, indices.end(),
                          [&](int64_t x, int64_t y) { return row[x] > row[y]; });

        for (size_t i = 0; i < keep; ++i) {
          const int64_t token = indices[i];
          if (curLen <= 1 && token == eos_) continue;
          const double logProb = static_cast<double>(row[token]) - normalizer;
          std::vector<int64_t> tokens = beams[b].tokens;
          tokens.push_back(token);
          const double score = beams[b].score + logProb;
          if (token == eos_) {
            finished.push_back({score, std::move(tokens)});
          } else {
            expanded.push_back({score, std::move(tokens)});
          }
        }
      }
      std::sort(expanded.begin(), expanded.end(),
                [](const Beam& a, const Beam& b) { return a.score > b.score; });
      if (expanded.size() > static_cast<size_t>(beamWidth)) expanded.resize(static_cast<size_t>(beamWidth));
      beams = std::move(expanded);

      // Every appended token adds a non-positive log-probability, so a raw
      // (pre length-penalty) beam score can only get worse as decoding
      // continues. Once beamWidth candidates have already finished with a
      // raw score no live beam can still reach, further steps cannot change
      // the eventual top-beamWidth set: stop. Without this, short words
      // still ran the full kMaxDecodeSteps because low-quality continuations
      // kept refilling the beam instead of the search naturally converging.
      if (!beams.empty() && finished.size() >= static_cast<size_t>(beamWidth)) {
        std::vector<double> finishedScores;
        finishedScores.reserve(finished.size());
        for (const auto& f : finished) finishedScores.push_back(f.score);
        std::nth_element(finishedScores.begin(), finishedScores.begin() + (beamWidth - 1),
                          finishedScores.end(), std::greater<double>());
        const double threshold = finishedScores[beamWidth - 1];
        const double bestLive =
            std::max_element(beams.begin(), beams.end(),
                              [](const Beam& a, const Beam& b) { return a.score < b.score; })
                ->score;
        if (bestLive < threshold) break;
      }
    }
    for (auto& beam : beams) finished.push_back(std::move(beam));

    std::unordered_map<std::string, double> unique;
    for (const auto& beam : finished) {
      const std::string native = detokenize(beam.tokens);
      if (native.empty() || !validGujaratiWord(native)) continue;
      const double lengthPenalty =
          std::pow((5.0 + static_cast<double>(std::max<size_t>(1, beam.tokens.size() - 1))) / 6.0, 1.0);
      const double normalizedScore = beam.score / lengthPenalty;
      const auto found = unique.find(native);
      if (found == unique.end() || normalizedScore > found->second) unique[native] = normalizedScore;
    }
    const std::vector<std::pair<std::string, double>> originals(unique.begin(), unique.end());
    for (const auto& [native, score] : originals) addOrthographicVariants(native, score, &unique);

    std::vector<std::pair<std::string, double>> ranked(unique.begin(), unique.end());
    std::sort(ranked.begin(), ranked.end(),
              [](const auto& a, const auto& b) { return a.second > b.second; });

    std::ostringstream json;
    json << '[';
    for (int index = 0; index < count && index < static_cast<int>(ranked.size()); ++index) {
      if (index) json << ',';
      json << "{\"native\":\"" << jsonEscape(ranked[index].first) << "\",\"logProb\":"
           << ranked[index].second << ",\"modelVersion\":\"" << jsonEscape(modelVersion_) << "\"}";
    }
    json << ']';
    return json.str();
  }

 private:
  std::string detokenize(const std::vector<int64_t>& tokens) const {
    std::string out;
    for (size_t index = 1; index < tokens.size(); ++index) {
      const int64_t token = tokens[index];
      if (token == eos_) break;
      if (token == bos_ || token == pad_ || token == unk_) continue;
      if (token >= 0 && static_cast<size_t>(token) < tgtVocab_.size()) {
        out += tgtVocab_[static_cast<size_t>(token)];
      }
    }
    return out;
  }

  void loadVocabulary(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open vocab.json");
    std::ostringstream buffer;
    buffer << input.rdbuf();
    const auto vocab = VocabJsonReader::parse(buffer.str());
    if (vocab.src.empty() || vocab.tgt.empty() || vocab.specialTokens.empty()) {
      throw std::runtime_error("invalid vocab.json");
    }
    for (size_t index = 0; index < vocab.src.size(); ++index) srcIndex_[vocab.src[index]] = static_cast<int64_t>(index);
    tgtVocab_ = vocab.tgt;
    const auto lookup = [&](const char* key, int64_t fallback) {
      const auto found = vocab.specialTokens.find(key);
      return found == vocab.specialTokens.end() ? fallback : found->second;
    };
    bos_ = lookup("bos", 0);
    pad_ = lookup("pad", 1);
    eos_ = lookup("eos", 2);
    unk_ = lookup("unk", 3);
    const auto langFound = srcIndex_.find("__gu__");
    langTokenId_ = langFound == srcIndex_.end() ? unk_ : langFound->second;
  }

  Ort::Env env_;
  Ort::SessionOptions options_;
  Ort::Session encoder_;
  Ort::Session decoder_;
  std::unordered_map<std::string, int64_t> srcIndex_;
  std::vector<std::string> tgtVocab_;
  int64_t bos_ = 0;
  int64_t pad_ = 1;
  int64_t eos_ = 2;
  int64_t unk_ = 3;
  int64_t langTokenId_ = 0;
  std::string modelVersion_{kVersion};
};

std::mutex modelMutex;
std::string loadedRoot;
// Process-lifetime model avoids ONNX Runtime teardown after its dylib globals.
Model* model = nullptr;
thread_local std::string result;
}  // namespace

AKSHAR_EXPORT const char* akshar_gu_model_version() { return kVersion; }

AKSHAR_EXPORT const char* akshar_gu_transliterate_nbest(
    const char* modelRoot, const char* roman, int count) {
  try {
    std::lock_guard<std::mutex> lock(modelMutex);
    const std::string root = modelRoot ? modelRoot : "";
    if (!model || loadedRoot != root) {
      model = new Model(root);
      loadedRoot = root;
    }
    result = model->nbest(roman ? roman : "", count);
  } catch (const std::exception& error) {
    result = "{\"error\":\"" + jsonEscape(error.what()) + "\"}";
  }
  return result.c_str();
}
