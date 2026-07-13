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

API="https://api.github.com/repos/HuangJian/librime-qjs/releases/tags/${LIBRIME_QJS_TAG}"
echo "Resolving librime-qjs Windows asset for ${LIBRIME_QJS_TAG} ..."
ASSET_URL="$(
  python3 - <<PY
import json, urllib.request
url = "$API"
req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "re-gu-trans"})
data = json.load(urllib.request.urlopen(req))
for a in data.get("assets", []):
    name = a.get("name", "")
    if "Windows" in name and ("x64" in name or "X64" in name):
        print(a["browser_download_url"])
        break
else:
    raise SystemExit("no Windows-x64 asset found")
PY
)"
ARCHIVE="$QJS_CACHE/$(basename "$ASSET_URL")"
if [[ ! -f "$ARCHIVE" ]]; then
  curl -fL -o "$ARCHIVE" "$ASSET_URL"
fi

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
  *.zip)
    unzip -q "$ARCHIVE" -d "$EXTRACT"
    ;;
  *)
    tar xf "$ARCHIVE" -C "$EXTRACT"
    ;;
esac

RIME_DLL="$(find "$EXTRACT" -iname 'rime.dll' | head -1)"
require_file "$RIME_DLL"

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

(
  cd "$ZIP_DIR"
  if command -v zip >/dev/null 2>&1; then
    zip -r "$OUT_DIR/re-gu-trans-${VERSION}-windows-x64.zip" .
  else
    python3 - <<PY
import shutil
shutil.make_archive("$OUT_DIR/re-gu-trans-${VERSION}-windows-x64", "zip", "$ZIP_DIR")
PY
  fi
)

echo "Windows package:"
ls -la "$OUT_DIR"/re-gu-trans-"${VERSION}"-windows-x64.zip
