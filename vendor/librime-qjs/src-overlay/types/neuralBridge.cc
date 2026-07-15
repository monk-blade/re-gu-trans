
// Optional Gujarati ONNX model bridge. The plugin and model pack remain
// independently installable; librime-qjs continues to load without them.
#if defined(_WIN32)
#include <windows.h>
#else
#include <dlfcn.h>
#endif
#include <mutex>
#include <stdexcept>
#include <vector>

namespace {
using AksharNBest = const char* (*)(const char*, const char*, int);
std::once_flag aksharModelOnce;
AksharNBest aksharNBest = nullptr;
std::string aksharModelRoot;

bool aksharAssetsExist(const std::string& root) {
  return Environment::fileExists(root + "/gujarati_xlit.int8.onnx") &&
         Environment::fileExists(root + "/vocab.tsv");
}

void aksharLoadModelBridge() {
  const auto user = Environment::getUserDataDir();
  const auto shared = Environment::getSharedDataDir();
  const std::vector<std::string> roots = {
      user + "/gujarati-model", shared + "/gujarati-model", user, shared};
  for (const auto& root : roots) {
    if (aksharAssetsExist(root)) {
      aksharModelRoot = root;
      break;
    }
  }
  if (aksharModelRoot.empty()) {
    std::fprintf(stderr, "[qjs] Gujarati model assets not found under user/shared data directories\n");
    return;
  }
#if defined(_WIN32)
  const char* filename = "rime-gujarati-model.dll";
#elif defined(__APPLE__)
  const char* filename = "librime-gujarati-model.dylib";
#else
  const char* filename = "librime-gujarati-model.so";
#endif
  const std::vector<std::string> libraries = {
      aksharModelRoot + "/" + filename, user + "/" + filename,
      shared + "/" + filename, filename};
  for (const auto& library : libraries) {
#if defined(_WIN32)
    HMODULE handle = LoadLibraryA(library.c_str());
    if (!handle) continue;
    aksharNBest = reinterpret_cast<AksharNBest>(
        GetProcAddress(handle, "akshar_gu_transliterate_nbest"));
#else
    void* handle = dlopen(library.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!handle) {
      const char* error = dlerror();
      if (error) std::fprintf(stderr, "[qjs] Gujarati model load failed: %s\n", error);
      continue;
    }
    aksharNBest = reinterpret_cast<AksharNBest>(
        dlsym(handle, "akshar_gu_transliterate_nbest"));
    if (!aksharNBest) {
      const char* error = dlerror();
      if (error) std::fprintf(stderr, "[qjs] Gujarati model symbol lookup failed: %s\n", error);
    }
#endif
    if (aksharNBest) return;
  }
  std::fprintf(stderr, "[qjs] Gujarati model plugin did not expose the required entrypoint\n");
}
}  // namespace

bool Environment::gujaratiModelAvailable() {
  std::call_once(aksharModelOnce, aksharLoadModelBridge);
  return aksharNBest != nullptr && !aksharModelRoot.empty();
}

std::string Environment::transliterateNBest(const std::string& roman, int count) {
  if (!gujaratiModelAvailable()) {
    throw std::runtime_error("Gujarati model plugin or model assets are unavailable");
  }
  const char* result = aksharNBest(aksharModelRoot.c_str(), roman.c_str(), count);
  if (!result) throw std::runtime_error("Gujarati model returned no result");
  return result;
}
