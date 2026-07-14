#!/usr/bin/env bash
# Build patched librime-qjs Windows plugin (rime.dll with writeFileAtomic overlay).
# Requires MSVC / cmake toolchain. Used by release Windows job.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common.sh
source "$SCRIPT_DIR/../common.sh"

BUILD_DIR="${BUILD_DIR:-$PACKAGE_ROOT/dist/librime-build-windows}"
OUT_DLL="${OUT_DLL:-$PACKAGE_ROOT/dist/plugins/rime.dll}"
JOBS="${JOBS:-4}"

mkdir -p "$(dirname "$OUT_DLL")"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

echo "Cloning librime @ $LIBRIME_TAG ..."
git clone --depth 1 --branch "$LIBRIME_TAG" https://github.com/rime/librime.git
cd librime

mkdir -p plugins
echo "Cloning librime-qjs @ $LIBRIME_QJS_TAG ..."
git clone --recursive --depth 1 --branch "$LIBRIME_QJS_TAG" \
  https://github.com/HuangJian/librime-qjs.git plugins/qjs
(
  cd plugins/qjs
  git submodule update --init --recursive
)

"$PACKAGE_ROOT/scripts/package/apply_qjs_writefile_atomic.sh" "$PWD/plugins/qjs"

# Windows librime build (HuangJian / rime docs use cmake + boost deps)
cmake -B build -G "Visual Studio 17 2022" -A x64 \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TEST=OFF \
  -DBUILD_SHARED_LIBS=ON || \
cmake -B build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_TEST=OFF \
  -DBUILD_SHARED_LIBS=ON

cmake --build build --config Release -j"$JOBS"

FOUND="$(find . -type f -iname 'rime.dll' 2>/dev/null | head -1 || true)"
if [[ -z "$FOUND" ]]; then
  # Some layouts emit librime-qjs.dll beside weasel rime.dll — prefer bundled rime.dll
  FOUND="$(find . -type f \( -iname 'librime-qjs.dll' -o -iname 'rime.dll' \) 2>/dev/null | head -1 || true)"
fi
if [[ -z "$FOUND" ]]; then
  echo "ERROR: patched Windows DLL not found after build" >&2
  find . -iname '*qjs*' -o -iname 'rime.dll' 2>/dev/null | head -40 || true
  exit 1
fi
cp -f "$FOUND" "$OUT_DLL"
echo "Built patched $OUT_DLL from $FOUND"
