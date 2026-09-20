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

# Use librime's pinned Windows dependency sources and build recipe. Directly
# configuring the top-level project leaves Boost/glog/OpenCC unresolved on a
# clean GitHub runner.
git submodule update --init --recursive

mkdir -p plugins
echo "Cloning librime-qjs @ $LIBRIME_QJS_TAG ..."
git clone --recursive --depth 1 --branch "$LIBRIME_QJS_TAG" \
  https://github.com/HuangJian/librime-qjs.git plugins/qjs
(
  cd plugins/qjs
  git submodule update --init --recursive
)

"$PACKAGE_ROOT/scripts/package/apply_qjs_writefile_atomic.sh" "$PWD/plugins/qjs"

# librime and librime-qjs both pin CMAKE_CXX_STANDARD to 17, but
# librime-qjs's own headers (qjs_candidate.h etc.) use C++20 designated
# initializers for JSCFunctionListEntry tables. GCC/Clang accept this as an
# extension even in C++17 mode (why the Linux/macOS builds are unaffected),
# but MSVC enforces it strictly and fails with C7555/C2065/etc. Bump both to
# the standard the code actually requires.
sed -i 's/CMAKE_CXX_STANDARD 17/CMAKE_CXX_STANDARD 20/' CMakeLists.txt
sed -i 's/CMAKE_CXX_STANDARD 17/CMAKE_CXX_STANDARD 20/' plugins/qjs/CMakeLists.txt

# Use Ninja with the MSVC environment supplied by ilammy/msvc-dev-cmd. This
# avoids coupling the build to a particular Visual Studio generator name.
cat > env.bat <<'EOF'
set RIME_ROOT=%CD%
set BOOST_ROOT=%RIME_ROOT%\deps\boost-1.89.0
set CMAKE_GENERATOR=Ninja
EOF

# The windows-latest runner's current MSVC (14.35+) requires an explicit
# opt-in to compile <stdatomic.h> (pulled in by quickjs-libc.c), or it fails
# with "fatal error C1189: C atomic support is not enabled". CL is read by
# cl.exe and prepended to every invocation, including the ones librime's own
# build.bat generates internally, so this reaches the actual failing compile
# without needing to patch quickjs's own build files.
export CL="/experimental:c11atomics"

# Git Bash/MSYS rewrites command arguments that look like POSIX paths.  That
# turns cmd.exe's `/c` switch into a drive path, so the batch files never run
# and only the cmd banner is emitted.  Disable conversion for these calls.
MSYS_NO_PATHCONV=1 cmd.exe /D /C install-boost.bat
# Boost 1.89 does not recognize the Visual Studio 18 environment as a named
# vcunk toolset. Bootstrap from the already-loaded MSVC developer shell using
# Boost's generic msvc configuration, then populate its generated headers.
BOOST_ROOT_WIN="$(native_path "$PWD/deps/boost-1.89.0")"
powershell.exe -NoProfile -NonInteractive -Command \
  "& { Set-Location -LiteralPath '$BOOST_ROOT_WIN'; & .\\bootstrap.bat msvc; if (\$LASTEXITCODE -ne 0) { exit \$LASTEXITCODE }; & .\\b2.exe headers; exit \$LASTEXITCODE }"
MSYS_NO_PATHCONV=1 cmd.exe /D /C build.bat deps
MSYS_NO_PATHCONV=1 cmd.exe /D /C build.bat librime

FOUND="$(find dist build -type f -iname 'rime.dll' 2>/dev/null | head -1 || true)"
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
