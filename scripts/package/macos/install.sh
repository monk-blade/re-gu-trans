#!/usr/bin/env bash
# Manual / zip installer for macOS (Apple Silicon).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DYLIB="$ROOT/plugin/librime-qjs.dylib"
PAYLOAD="$ROOT/payload/rime"
PLUGIN_DIR="/Library/Input Methods/Squirrel.app/Contents/Frameworks/rime-plugins"
SQUIRREL="/Library/Input Methods/Squirrel.app"

if [[ ! -d "$SQUIRREL" ]]; then
  echo "ERROR: Squirrel not installed at $SQUIRREL" >&2
  echo "Download: https://github.com/rime/squirrel/releases" >&2
  exit 1
fi
if [[ ! -f "$DYLIB" ]]; then
  echo "ERROR: missing $DYLIB" >&2
  exit 1
fi

echo "Installing librime-qjs.dylib (admin)..."
sudo mkdir -p "$PLUGIN_DIR"
sudo cp -f "$DYLIB" "$PLUGIN_DIR/librime-qjs.dylib"
sudo chmod 755 "$PLUGIN_DIR/librime-qjs.dylib"
sudo codesign --force --sign - "$PLUGIN_DIR/librime-qjs.dylib" || true

RIME="${HOME}/Library/Rime"
mkdir -p "$RIME/js/lm" "$RIME/run"
cp -f "$PAYLOAD/gujarati.schema.yaml" "$RIME/"
cp -f "$PAYLOAD/gujarati.dict.yaml" "$RIME/"
cp -f "$PAYLOAD/gujarati_apple.dict.yaml" "$RIME/" 2>/dev/null || true
cp -f "$PAYLOAD/"*.js "$RIME/" 2>/dev/null || true
cp -f "$PAYLOAD/gu_lexicon_blob.json" "$RIME/" 2>/dev/null || true
cp -f "$PAYLOAD/js/"*.js "$RIME/js/"
cp -f "$PAYLOAD/js/gu_lexicon_blob.json" "$RIME/js/"
cp -f "$PAYLOAD/js/lm/"* "$RIME/js/lm/"

CUSTOM="$RIME/default.custom.yaml"
if [[ ! -f "$CUSTOM" ]]; then
  cp -f "$PAYLOAD/default.custom.yaml" "$CUSTOM"
elif ! grep -q 'schema: gujarati' "$CUSTOM" 2>/dev/null; then
  echo "" >> "$CUSTOM"
  cat "$PAYLOAD/default.custom.yaml" >> "$CUSTOM"
fi

"$SQUIRREL/Contents/MacOS/Squirrel" --reload 2>/dev/null || true
echo "Done. Select Squirrel → Gujarati and Deploy if needed."
