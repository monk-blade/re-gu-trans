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
constexpr const char* kVersion = "gu-ctc-v1";

struct Beam {
  double score{0};
  std::vector<int64_t> path;
};

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
    std::vector<Beam> beams(1);
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
      std::vector<Beam> expanded;
      expanded.reserve(beams.size() * keep);
      for (const auto& beam : beams) {
        for (size_t index = 0; index < keep; ++index) {
          const int64_t token = tokens[index];
          Beam next = beam;
          next.score += static_cast<double>(row[token]) - normalizer;
          next.path.push_back(token);
          expanded.push_back(std::move(next));
        }
      }
      std::partial_sort(expanded.begin(), expanded.begin() + std::min(beamWidth, expanded.size()),
                        expanded.end(), [](const Beam& a, const Beam& b) { return a.score > b.score; });
      if (expanded.size() > beamWidth) expanded.resize(beamWidth);
      beams = std::move(expanded);
    }
    std::unordered_map<std::string, double> unique;
    for (const auto& beam : beams) {
      std::string native;
      int64_t previous = -1;
      for (int64_t token : beam.path) {
        if (token != 0 && token != previous && token < static_cast<int64_t>(outputVocab_.size())) {
          native += outputVocab_[static_cast<size_t>(token)];
        }
        previous = token;
      }
      if (!native.empty() && (!unique.count(native) || beam.score > unique[native])) unique[native] = beam.score;
    }
    std::vector<std::pair<std::string, double>> ranked(unique.begin(), unique.end());
    std::sort(ranked.begin(), ranked.end(),
              [](const auto& a, const auto& b) { return a.second > b.second; });
    std::ostringstream json;
    json << '[';
    for (int index = 0; index < count && index < static_cast<int>(ranked.size()); ++index) {
      if (index) json << ',';
      json << "{\"native\":\"" << jsonEscape(ranked[index].first) << "\",\"logProb\":"
           << ranked[index].second << ",\"modelVersion\":\"" << kVersion << "\"}";
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
    std::getline(input, inputLine);
    std::getline(input, outputLine);
    auto inputs = splitTabs(inputLine);
    outputVocab_ = splitTabs(outputLine);
    if (inputs.empty() || inputs[0] != "input" || outputVocab_.empty() || outputVocab_[0] != "output") {
      throw std::runtime_error("invalid vocab.tsv");
    }
    inputs.erase(inputs.begin());
    outputVocab_.erase(outputVocab_.begin());
    for (size_t index = 0; index < inputs.size(); ++index) inputIndex_[inputs[index]] = index;
  }

  Ort::Env env_;
  Ort::SessionOptions options_;
  Ort::Session session_;
  std::unordered_map<std::string, int64_t> inputIndex_;
  std::vector<std::string> outputVocab_;
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
