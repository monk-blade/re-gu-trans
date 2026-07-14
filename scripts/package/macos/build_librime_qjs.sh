#!/usr/bin/env bash
# Build librime-qjs.dylib for macOS from source + writeFileAtomic overlay.
# Prefer this over unpatched HuangJian prebuilts for Release learning support.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common.sh
source "$SCRIPT_DIR/../common.sh"

BUILD_DIR="${BUILD_DIR:-$PACKAGE_ROOT/dist/librime-build-macos}"
OUT_DYLIB="${OUT_DYLIB:-$PACKAGE_ROOT/dist/plugins/librime-qjs.dylib}"
JOBS="${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || true)}"
if ! [[ "$JOBS" =~ ^[1-9][0-9]*$ ]]; then JOBS=4; fi

mkdir -p "$(dirname "$OUT_DYLIB")"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

echo "Cloning librime @ $LIBRIME_TAG ..."
git clone --depth 1 --branch "$LIBRIME_TAG" https://github.com/rime/librime.git
cd librime

# Build pinned third-party dependencies into the local source prefix. This
# keeps CI/release builds independent of a developer's Homebrew inventory.
git submodule update --init --depth 1 \
  deps/glog deps/leveldb deps/marisa-trie deps/opencc deps/yaml-cpp

mkdir -p plugins
echo "Cloning librime-qjs @ $LIBRIME_QJS_TAG ..."
git clone --recursive --depth 1 --branch "$LIBRIME_QJS_TAG" \
  https://github.com/HuangJian/librime-qjs.git plugins/qjs
(
  cd plugins/qjs
  git submodule update --init --recursive
)

"$PACKAGE_ROOT/scripts/package/apply_qjs_writefile_atomic.sh" "$PWD/plugins/qjs"

export CMAKE_BUILD_PARALLEL_LEVEL="$JOBS"
make -f deps.mk NOPARALLEL=1 -j"$JOBS" glog leveldb marisa-trie opencc yaml-cpp
cmake -S . -B build \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DBUILD_TEST=OFF \
  -DBUILD_MERGED_PLUGINS=OFF \
  -DENABLE_EXTERNAL_PLUGINS=ON \
  -DENABLE_LOGGING=ON \
  -DCMAKE_PREFIX_PATH="$PWD"
cmake --build build --parallel "$JOBS"

FOUND="$(find . -type f -name 'librime-qjs.dylib' 2>/dev/null | head -1 || true)"
if [[ -z "$FOUND" ]]; then
  echo "ERROR: librime-qjs.dylib not found after build" >&2
  find . -name '*qjs*' 2>/dev/null | head -40 || true
  exit 1
fi
cp -f "$FOUND" "$OUT_DYLIB"
chmod 755 "$OUT_DYLIB"
codesign --force --sign - "$OUT_DYLIB" 2>/dev/null || true
echo "Built patched $OUT_DYLIB"
