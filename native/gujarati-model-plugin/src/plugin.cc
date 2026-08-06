#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <memory>
#include <map>
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
constexpr const char* kVersion = "gu-model-plugin-v2";
constexpr const char* kLongIMatra = "\xE0\xAB\x80";
constexpr const char* kShortIMatra = "\xE0\xAA\xBF";
constexpr double kOrthographicVariantPenalty = 0.5;

struct PrefixScore {
  double blank{-INFINITY};
  double nonblank{-INFINITY};
};

double logAdd(double a, double b) {
  if (!std::isfinite(a)) return b;
  if (!std::isfinite(b)) return a;
  const double maximum = std::max(a, b);
  return maximum + std::log(std::exp(a - maximum) + std::exp(b - maximum));
}

double totalScore(const PrefixScore& score) { return logAdd(score.blank, score.nonblank); }

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

std::vector<std::string> splitTabs(const std::string& line) {
  std::vector<std::string> values;
  std::string value;
  std::istringstream stream(line);
  while (std::getline(stream, value, '\t')) values.push_back(value);
  return values;
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

class Model {
 public:
  explicit Model(const std::string& root)
      : env_(ORT_LOGGING_LEVEL_WARNING, "akshar-gu"),
        options_(),
        session_(nullptr) {
    options_.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
    options_.SetIntraOpNumThreads(1);
    loadVocabulary(root + "/vocab.tsv");
#if defined(_WIN32)
    std::wstring modelPath(root.begin(), root.end());
    modelPath += L"\\gujarati_xlit.int8.onnx";
    session_ = Ort::Session(env_, modelPath.c_str(), options_);
#else
    session_ = Ort::Session(env_, (root + "/gujarati_xlit.int8.onnx").c_str(), options_);
#endif
  }

  std::string nbest(const std::string& roman, int requested) {
    if (!validRomanWord(roman)) return "[]";
    const int count = std::max(1, std::min(8, requested));
    std::vector<int64_t> input;
    input.reserve(roman.size());
    for (unsigned char ch : roman) {
      const auto found = inputIndex_.find(std::string(1, static_cast<char>(std::tolower(ch))));
      input.push_back(found == inputIndex_.end() ? 1 : found->second);
    }
    if (input.empty()) input.push_back(1);
    std::vector<int64_t> shape{1, static_cast<int64_t>(input.size())};
    auto memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    auto tensor = Ort::Value::CreateTensor<int64_t>(
        memory, input.data(), input.size(), shape.data(), shape.size());
    const char* inputNames[] = {"roman_ids"};
    const char* outputNames[] = {"logits"};
    auto outputs = session_.Run(Ort::RunOptions{nullptr}, inputNames, &tensor, 1, outputNames, 1);
    const auto outputShape = outputs[0].GetTensorTypeAndShapeInfo().GetShape();
    if (outputShape.size() != 3 || outputShape[0] != 1) throw std::runtime_error("invalid logits shape");
    const int64_t frames = outputShape[1];
    const int64_t vocab = outputShape[2];
    const float* logits = outputs[0].GetTensorData<float>();
    const size_t beamWidth = static_cast<size_t>(std::max(8, count * 2));
    std::map<std::vector<int64_t>, PrefixScore> beams;
    beams[{}] = PrefixScore{0.0, -INFINITY};
    for (int64_t frame = 0; frame < frames; ++frame) {
      const float* row = logits + frame * vocab;
      const float maximum = *std::max_element(row, row + vocab);
      double sum = 0;
      for (int64_t token = 0; token < vocab; ++token) sum += std::exp(row[token] - maximum);
      const double normalizer = maximum + std::log(sum);
      std::vector<int64_t> tokens(static_cast<size_t>(vocab));
      for (int64_t token = 0; token < vocab; ++token) tokens[static_cast<size_t>(token)] = token;
      const size_t keep = std::min(beamWidth, tokens.size());
      std::partial_sort(tokens.begin(), tokens.begin() + keep, tokens.end(),
                        [&](int64_t a, int64_t b) { return row[a] > row[b]; });
      tokens.resize(keep);
      if (std::find(tokens.begin(), tokens.end(), 0) == tokens.end()) tokens.push_back(0);
      std::map<std::vector<int64_t>, PrefixScore> expanded;
      for (const auto& [prefix, score] : beams) {
        const double total = totalScore(score);
        auto& same = expanded[prefix];
        same.blank = logAdd(same.blank, total + static_cast<double>(row[0]) - normalizer);
        for (size_t index = 0; index < keep; ++index) {
          const int64_t token = tokens[index];
          if (token == 0) continue;
          const double probability = static_cast<double>(row[token]) - normalizer;
          if (!prefix.empty() && prefix.back() == token) {
            same.nonblank = logAdd(same.nonblank, score.nonblank + probability);
            auto repeated = prefix;
            repeated.push_back(token);
            auto& next = expanded[repeated];
            next.nonblank = logAdd(next.nonblank, score.blank + probability);
          } else {
            auto nextPrefix = prefix;
            nextPrefix.push_back(token);
            auto& next = expanded[nextPrefix];
            next.nonblank = logAdd(next.nonblank, total + probability);
          }
        }
      }
      std::vector<std::pair<std::vector<int64_t>, PrefixScore>> ranked(
          expanded.begin(), expanded.end());
      const size_t retained = std::min(beamWidth, ranked.size());
      std::partial_sort(
          ranked.begin(), ranked.begin() + retained, ranked.end(),
          [](const auto& a, const auto& b) { return totalScore(a.second) > totalScore(b.second); });
      beams.clear();
      for (size_t index = 0; index < retained; ++index) beams.emplace(std::move(ranked[index]));
    }
    std::unordered_map<std::string, double> unique;
    for (const auto& [prefix, score] : beams) {
      std::string native;
      for (int64_t token : prefix) {
        if (token != 0 && token < static_cast<int64_t>(outputVocab_.size())) {
          native += outputVocab_[static_cast<size_t>(token)];
        }
      }
      const double probability = totalScore(score);
      if (validGujaratiWord(native) && (!unique.count(native) || probability > unique[native])) {
        unique[native] = probability;
      }
    }
    const std::vector<std::pair<std::string, double>> originals(unique.begin(), unique.end());
    for (const auto& [native, probability] : originals) {
      addOrthographicVariants(native, probability, &unique);
    }
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
  void loadVocabulary(const std::string& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot open vocab.tsv");
    std::string inputLine;
    std::string outputLine;
    std::string versionLine;
    std::getline(input, inputLine);
    std::getline(input, outputLine);
    std::getline(input, versionLine);
    auto inputs = splitTabs(inputLine);
    outputVocab_ = splitTabs(outputLine);
    if (inputs.empty() || inputs[0] != "input" || outputVocab_.empty() || outputVocab_[0] != "output") {
      throw std::runtime_error("invalid vocab.tsv");
    }
    inputs.erase(inputs.begin());
    outputVocab_.erase(outputVocab_.begin());
    for (size_t index = 0; index < inputs.size(); ++index) inputIndex_[inputs[index]] = index;
    const auto version = splitTabs(versionLine);
    if (version.size() >= 2 && version[0] == "version") modelVersion_ = version[1];
  }

  Ort::Env env_;
  Ort::SessionOptions options_;
  Ort::Session session_;
  std::unordered_map<std::string, int64_t> inputIndex_;
  std::vector<std::string> outputVocab_;
  std::string modelVersion_{"gu-ctc-v1"};
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
