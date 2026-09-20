#!/usr/bin/env bash
# Apply writeFileAtomic overlay onto a HuangJian/librime-qjs source checkout.
# Usage: apply_qjs_writefile_atomic.sh /path/to/librime-qjs
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="${1:?path to librime-qjs checkout}"
OVER="$ROOT/vendor/librime-qjs/src-overlay/types"

test -d "$SRC/src/types" || { echo "not a librime-qjs tree: $SRC"; exit 1; }

# The pinned loader uses GCC's constructor attribute for Windows too. MSVC
# does not parse that attribute, so register the same initializer through the
# CRT's XCU section while leaving MinGW/Clang builds on the upstream path.
NODE_LOADER="$SRC/src/patch/quickjs/node_module_loader.c"
python3 - "$NODE_LOADER" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = r'''#ifdef _WIN32
#include <windows.h>
__attribute__((constructor)) void initBaseFolder() {
  char path[LOADER_PATH_MAX];
  GetModuleFileNameA(NULL, path, LOADER_PATH_MAX);
  char* last_slash = strrchr(path, '\\');
  if (last_slash) {
    *last_slash = '\0';
    setQjsBaseFolder(path);
  }
}
#endif'''
new = r'''#ifdef _WIN32
#include <windows.h>
#ifdef _MSC_VER
#pragma section(".CRT$XCU", read)
static void __cdecl initBaseFolder(void) {
  char path[LOADER_PATH_MAX];
  GetModuleFileNameA(NULL, path, LOADER_PATH_MAX);
  char* last_slash = strrchr(path, '\\');
  if (last_slash) {
    *last_slash = '\0';
    setQjsBaseFolder(path);
  }
}
__declspec(allocate(".CRT$XCU")) void (__cdecl *initBaseFolderInitializer)(void) = initBaseFolder;
#else
__attribute__((constructor)) void initBaseFolder(void) {
  char path[LOADER_PATH_MAX];
  GetModuleFileNameA(NULL, path, LOADER_PATH_MAX);
  char* last_slash = strrchr(path, '\\');
  if (last_slash) {
    *last_slash = '\0';
    setQjsBaseFolder(path);
  }
}
#endif
#endif'''
if old not in text:
    raise SystemExit(f"node loader constructor block not found: {path}")
if "initBaseFolderInitializer" not in text:
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched MSVC CRT initializer", path)
else:
    print("MSVC CRT initializer already patched", path)
PY
cp -f "$OVER/environment.h" "$SRC/src/types/environment.h"

# Append implementation once
if ! grep -q 'writeFileAtomic' "$SRC/src/types/environment.cc"; then
  # Fix include for filesystem in header via cc
  if ! grep -q 'filesystem' "$SRC/src/types/environment.cc"; then
    sed -i.bak '1a\
#include <filesystem>
' "$SRC/src/types/environment.cc" || true
  fi
  cat "$OVER/writeFileAtomic.cc" >> "$SRC/src/types/environment.cc"
fi
if ! grep -q 'transliterateNBest' "$SRC/src/types/environment.cc"; then
  cat "$OVER/neuralBridge.cc" >> "$SRC/src/types/environment.cc"
fi

# Bind JS API
QJS_ENV="$SRC/src/types/qjs_environment.h"
QJS_ENV_PY="$QJS_ENV"
if command -v cygpath >/dev/null 2>&1; then
  QJS_ENV_PY="$(cygpath -m "$QJS_ENV")"
fi
if ! grep -q 'writeFileAtomic' "$QJS_ENV"; then
  python3 - "$QJS_ENV_PY" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
needle = "DEFINE_CFUNCTION_ARGC(fileExists, 1,"
insert = '''
  DEFINE_CFUNCTION_ARGC(writeFileAtomic, 2, {
    std::string path = engine.toStdString(argv[0]);
    std::string content = engine.toStdString(argv[1]);
    if (path.empty()) {
      throw JsException(JsErrorType::SYNTAX, "writeFileAtomic path must be a string");
    }
    try {
      Environment::writeFileAtomic(path, content);
    } catch (const std::exception& e) {
      throw JsException(JsErrorType::GENERIC, e.what());
    }
    return engine.null();
  })

'''
if needle not in text:
    raise SystemExit('needle not found in qjs_environment.h')
if 'writeFileAtomic' not in text:
    text = text.replace(needle, insert + needle, 1)
    text = text.replace(
        'WITH_FUNCTIONS(loadFile, 1, fileExists, 1, getRimeInfo, 0, popen, 1)',
        'WITH_FUNCTIONS(loadFile, 1, fileExists, 1, writeFileAtomic, 2, getRimeInfo, 0, popen, 1)',
    )
    p.write_text(text, encoding="utf-8")
    print('patched', p)
else:
    print('already patched', p)
PY
fi

if ! grep -q 'transliterateNBest' "$QJS_ENV"; then
  python3 - "$QJS_ENV_PY" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
needle = "DEFINE_CFUNCTION_ARGC(fileExists, 1,"
insert = '''
  DEFINE_CFUNCTION(gujaratiModelAvailable, {
    return engine.wrap(Environment::gujaratiModelAvailable());
  })

  DEFINE_CFUNCTION_ARGC(transliterateNBest, 2, {
    std::string roman = engine.toStdString(argv[0]);
    int count = argc > 1 ? engine.toInt(argv[1]) : 4;
    try {
      return engine.wrap(Environment::transliterateNBest(roman, count));
    } catch (const std::exception& e) {
      throw JsException(JsErrorType::GENERIC, e.what());
    }
  })

'''
if needle not in text:
    raise SystemExit('needle not found in qjs_environment.h')
text = text.replace(needle, insert + needle, 1)
text = text.replace(
    'WITH_FUNCTIONS(loadFile, 1, fileExists, 1, writeFileAtomic, 2, getRimeInfo, 0, popen, 1)',
    'WITH_FUNCTIONS(loadFile, 1, fileExists, 1, writeFileAtomic, 2, gujaratiModelAvailable, 0, transliterateNBest, 2, getRimeInfo, 0, popen, 1)',
)
p.write_text(text, encoding="utf-8")
print('patched Gujarati model bridge', p)
PY
fi

echo "writeFileAtomic overlay applied to $SRC"
