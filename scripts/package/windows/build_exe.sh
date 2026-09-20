#!/usr/bin/env bash
# Build the Windows .exe installer on top of the existing zip kit.
#
# Reuses build_zip.sh's staged output (dist/windows-zip/{payload,plugin,
# install.ps1,...}) as the NSIS installer's source tree, so the actual
# deployment logic is defined once, in install.ps1.
#
# Requires makensis (NSIS) on PATH. On windows-latest GitHub runners:
#   choco install nsis -y

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common.sh
source "$SCRIPT_DIR/../common.sh"

VERSION="$(resolve_version)"
export VERSION
DIST="$PACKAGE_ROOT/dist"
ZIP_DIR="$DIST/windows-zip"
OUT_DIR="$DIST/packages"

if [[ ! -d "$ZIP_DIR/payload" || ! -f "$ZIP_DIR/install.ps1" ]]; then
  echo "== staging windows-zip kit (build_zip.sh) first =="
  "$SCRIPT_DIR/build_zip.sh"
fi

command -v makensis >/dev/null 2>&1 || {
  echo "FAIL: makensis (NSIS) not found on PATH" >&2
  echo "  Windows: choco install nsis -y" >&2
  echo "  Linux (cross-build, untested for signing): apt-get install nsis" >&2
  exit 1
}

mkdir -p "$OUT_DIR"
SRC_DIR_NATIVE="$ZIP_DIR"
if command -v cygpath >/dev/null 2>&1; then
  SRC_DIR_NATIVE="$(cygpath -w "$ZIP_DIR")"
fi

makensis \
  "-DVERSION=$VERSION" \
  "-DSRC_DIR=$SRC_DIR_NATIVE" \
  -O"$DIST/makensis.log" \
  "$SCRIPT_DIR/installer.nsi"

BUILT_EXE="$SCRIPT_DIR/re-gu-trans-${VERSION}-windows-x64-setup.exe"
if [[ ! -f "$BUILT_EXE" ]]; then
  echo "FAIL: expected installer not found at $BUILT_EXE" >&2
  cat "$DIST/makensis.log" >&2 || true
  exit 1
fi
mv -f "$BUILT_EXE" "$OUT_DIR/"

echo "Windows installer:"
ls -la "$OUT_DIR/re-gu-trans-${VERSION}-windows-x64-setup.exe"
