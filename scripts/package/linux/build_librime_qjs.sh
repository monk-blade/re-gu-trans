#!/usr/bin/env bash
# Build librime-qjs.so for Linux by compiling librime + HuangJian/librime-qjs plugin.
#
# Env:
#   LIBRIME_QJS_TAG  default v1.3.0
#   LIBRIME_TAG      default 1.16.1
#   BUILD_DIR        default $PACKAGE_ROOT/dist/librime-build
#   OUT_SO           default $PACKAGE_ROOT/dist/plugins/librime-qjs.so

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

mkdir -p plugins
echo "Cloning librime-qjs @ $LIBRIME_QJS_TAG into plugins/qjs ..."
git clone --recursive --depth 1 --branch "$LIBRIME_QJS_TAG" \
  https://github.com/HuangJian/librime-qjs.git plugins/qjs

# Ensure QuickJS submodule is present (depth-1 clone can miss nested content)
(
  cd plugins/qjs
  git submodule update --init --recursive
)

# librime Makefile drives cmake + plugins (see HuangJian doc/build-linux.md)
export CMAKE_BUILD_PARALLEL_LEVEL="$JOBS"
if [[ -f Makefile ]]; then
  # Prefer Release; skip tests for packaging speed
  make -j"$JOBS" release 2>/dev/null || make -j"$JOBS"
else
  cmake -B build -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=ON \
    -DBUILD_TEST=OFF
  cmake --build build -j"$JOBS"
fi

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
