#!/usr/bin/env bash
# Build librime-qjs.so for Linux by compiling librime + HuangJian/librime-qjs plugin.
#
# Env:
#   LIBRIME_QJS_TAG  default v1.3.0
#   LIBRIME_TAG      default 1.16.1
#   BUILD_DIR        default $PACKAGE_ROOT/dist/librime-build
#   OUT_SO           default $PACKAGE_ROOT/dist/plugins/librime-qjs.so
#
# Ubuntu 22.04 / GCC patches applied after clone:
#   - __FILE_NAME__ → __FILE__ (Clang-only macro used by librime-qjs)
#   - glog IsGoogleLoggingInitialized shim (not public on distro libglog)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common.sh
source "$SCRIPT_DIR/../common.sh"

BUILD_DIR="${BUILD_DIR:-$PACKAGE_ROOT/dist/librime-build}"
OUT_SO="${OUT_SO:-$PACKAGE_ROOT/dist/plugins/librime-qjs.so}"
JOBS="${JOBS:-$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)}"

mkdir -p "$(dirname "$OUT_SO")"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

echo "Cloning librime @ $LIBRIME_TAG ..."
git clone --depth 1 --branch "$LIBRIME_TAG" https://github.com/rime/librime.git
cd librime

# --- patch: Ubuntu 22.04 libglog lacks public google::IsGoogleLoggingInitialized ---
SETUP_CC="src/rime/setup.cc"
if [[ -f "$SETUP_CC" ]] && grep -q 'IsGoogleLoggingInitialized' "$SETUP_CC"; then
  echo "Patching $SETUP_CC for older libglog ..."
  python3 - "$SETUP_CC" <<'PY'
from pathlib import Path
import sys
path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = """  if (google::IsGoogleLoggingInitialized()) {
    LOG(WARNING) << "Glog is already initialized.";
  } else {
    google::InitGoogleLogging(app_name);
  }"""
new = """  // re-gu-trans: distro libglog (Ubuntu 22.04) often lacks public
  // google::IsGoogleLoggingInitialized(); use a process-local guard.
  static bool glog_initialized = false;
  if (glog_initialized) {
    LOG(WARNING) << "Glog is already initialized.";
  } else {
    google::InitGoogleLogging(app_name);
    glog_initialized = true;
  }"""
if old not in text:
    # tolerant whitespace match
    import re
    pat = re.compile(
        r"if\s*\(\s*google::IsGoogleLoggingInitialized\s*\(\s*\)\s*\)\s*\{.*?"
        r"google::InitGoogleLogging\s*\(\s*app_name\s*\)\s*;\s*\}",
        re.S,
    )
    text2, n = pat.subn(new.strip(), text, count=1)
    if n != 1:
        raise SystemExit(f"failed to patch {path}: IsGoogleLoggingInitialized block not found")
    path.write_text(text2, encoding="utf-8")
else:
    path.write_text(text.replace(old, new), encoding="utf-8")
print(f"patched {path}")
PY
fi

mkdir -p plugins
echo "Cloning librime-qjs @ $LIBRIME_QJS_TAG into plugins/qjs ..."
git clone --recursive --depth 1 --branch "$LIBRIME_QJS_TAG" \
  https://github.com/HuangJian/librime-qjs.git plugins/qjs

# Ensure QuickJS submodule is present (depth-1 clone can miss nested content)
(
  cd plugins/qjs
  git submodule update --init --recursive
)

# Atomic learning API
"$PACKAGE_ROOT/scripts/package/apply_qjs_writefile_atomic.sh" "$PWD/plugins/qjs"

# --- patch: __FILE_NAME__ is Clang-only; GCC needs __FILE__ ---
echo "Patching librime-qjs __FILE_NAME__ → __FILE__ for GCC ..."
find plugins/qjs -type f \( -name '*.cc' -o -name '*.cpp' -o -name '*.h' -o -name '*.hpp' \) \
  -print0 | xargs -0 sed -i 's/__FILE_NAME__/__FILE__/g'

# Configure directly so packaging flags, including the test exclusion, are
# applied consistently across distro toolchains (see HuangJian doc/build-linux.md).
export CMAKE_BUILD_PARALLEL_LEVEL="$JOBS"
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DBUILD_TEST=OFF \
  -DBUILD_MERGED_PLUGINS=OFF \
  -DENABLE_EXTERNAL_PLUGINS=ON \
  -DCMAKE_SKIP_RPATH=ON
cmake --build build -j"$JOBS"

FOUND=""
while IFS= read -r cand; do
  FOUND="$cand"
  break
done < <(find . -type f \( -name 'librime-qjs.so' -o -name 'librime-qjs.so.*' \) 2>/dev/null | head -20)

if [[ -z "$FOUND" ]]; then
  echo "ERROR: librime-qjs.so not found after build." >&2
  find . -name '*qjs*' 2>/dev/null | head -50 || true
  ls -la build/lib 2>/dev/null || true
  ls -la build/lib/rime-plugins 2>/dev/null || true
  exit 1
fi

cp -f "$FOUND" "$OUT_SO"
chmod 755 "$OUT_SO"
echo "Built plugin → $OUT_SO (from $FOUND)"
ls -la "$OUT_SO"
file "$OUT_SO" || true
