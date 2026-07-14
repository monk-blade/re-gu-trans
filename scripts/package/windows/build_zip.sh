#!/usr/bin/env bash
# Build Windows zip kit: payload + librime-qjs Weasel rime.dll + install.ps1
# Runs on Windows (Git Bash / MSYS) or Linux with 7z for extracting .7z assets.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common.sh
source "$SCRIPT_DIR/../common.sh"

VERSION="$(resolve_version)"
export VERSION
DIST="$PACKAGE_ROOT/dist"
PAYLOAD="$DIST/payload-windows"
ZIP_DIR="$DIST/windows-zip"
OUT_DIR="$DIST/packages"
QJS_CACHE="$DIST/qjs-windows"

mkdir -p "$OUT_DIR" "$QJS_CACHE"

"$SCRIPT_DIR/../stage_payload.sh" "$PAYLOAD" windows

# Prefer patched rime.dll built from source + overlay (required for learning).
RIME_DLL="${OUT_DLL:-$DIST/plugins/rime.dll}"
REQUIRE_PATCHED_QJS="${REQUIRE_PATCHED_QJS:-1}"
if [[ ! -f "$RIME_DLL" ]]; then
  if [[ "$REQUIRE_PATCHED_QJS" == "1" ]]; then
    echo "Building patched Windows rime.dll from source..."
    chmod +x "$SCRIPT_DIR/build_librime_qjs.sh"
    "$SCRIPT_DIR/build_librime_qjs.sh"
    RIME_DLL="${OUT_DLL:-$DIST/plugins/rime.dll}"
  else
    ASSET_URL="$(resolve_qjs_asset_url windows-x64)"
    echo "WARN: downloading unpatched librime-qjs: $ASSET_URL" >&2
    ARCHIVE="$QJS_CACHE/$(basename "$ASSET_URL")"
    download_file "$ASSET_URL" "$ARCHIVE"
    EXTRACT="$QJS_CACHE/extract"
    rm -rf "$EXTRACT"
    mkdir -p "$EXTRACT"
    case "$ARCHIVE" in
      *.7z)
        if command -v 7z >/dev/null 2>&1; then
          7z x -o"$EXTRACT" "$ARCHIVE" >/dev/null
        elif command -v 7za >/dev/null 2>&1; then
          7za x -o"$EXTRACT" "$ARCHIVE" >/dev/null
        else
          echo "ERROR: need 7z to extract $ARCHIVE" >&2
          exit 1
        fi
        ;;
      *.zip) unzip -q "$ARCHIVE" -d "$EXTRACT" ;;
      *) tar xf "$ARCHIVE" -C "$EXTRACT" ;;
    esac
    RIME_DLL="$(find "$EXTRACT" -iname 'rime.dll' | head -1)"
  fi
fi
require_file "$RIME_DLL"
"$PACKAGE_ROOT/scripts/package/verify_qjs_plugin.sh" "$RIME_DLL"

rm -rf "$ZIP_DIR"
mkdir -p "$ZIP_DIR/payload" "$ZIP_DIR/plugin"
cp -a "$PAYLOAD/." "$ZIP_DIR/payload/"
cp -f "$RIME_DLL" "$ZIP_DIR/plugin/rime.dll"
# Include any companion DLLs next to rime.dll
DLL_DIR="$(dirname "$RIME_DLL")"
find "$DLL_DIR" -maxdepth 1 -iname '*.dll' ! -iname 'rime.dll' -exec cp -f {} "$ZIP_DIR/plugin/" \;

cp -f "$SCRIPT_DIR/install.ps1" "$ZIP_DIR/install.ps1"
cp -f "$SCRIPT_DIR/install.bat" "$ZIP_DIR/install.bat"

cat > "$ZIP_DIR/README.txt" <<EOF
re-gu-trans ${VERSION} (Windows x64)
Prerequisites: Weasel (小狼毫) — https://github.com/rime/weasel/releases
Pinned librime-qjs / rime.dll: ${LIBRIME_QJS_TAG} (librime ${LIBRIME_TAG})

1. Exit Weasel from the system tray.
2. Right-click install.bat → Run as administrator
   (or: powershell -ExecutionPolicy Bypass -File install.ps1)
3. Deploy from Weasel tray menu.
4. Select Gujarati Transliteration.
EOF

zip_dir_contents "$ZIP_DIR" "$OUT_DIR/re-gu-trans-${VERSION}-windows-x64.zip"

echo "Windows package:"
ls -la "$OUT_DIR"/re-gu-trans-"${VERSION}"-windows-x64.zip
"$SCRIPT_DIR/../validate_archive.sh" "$OUT_DIR/re-gu-trans-${VERSION}-windows-x64.zip"
