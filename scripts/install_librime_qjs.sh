#!/usr/bin/env bash
# Install librime-qjs into system Squirrel (requires admin + Terminal Full Disk Access)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/vendor/librime-qjs/librime-qjs.dylib"
if [[ ! -f "$SRC" ]]; then
  echo "Downloading librime-qjs release..."
  TMP=$(mktemp -d)
  curl -sL -o "$TMP/qjs.tar.bz2" \
    "https://github.com/HuangJian/librime-qjs/releases/download/latest/librime-qjs-fa3894b-macOS-ARM64.tar.bz2"
  tar xjf "$TMP/qjs.tar.bz2" -C "$TMP"
  mkdir -p "$ROOT/vendor/librime-qjs"
  cp "$TMP/rime-plugins/librime-qjs.dylib" "$SRC"
  cp "$TMP/qjs" "$ROOT/vendor/librime-qjs/qjs" 2>/dev/null || true
  cp "$TMP/version-info.txt" "$ROOT/vendor/librime-qjs/" 2>/dev/null || true
fi

PLUGIN_DIR="/Library/Input Methods/Squirrel.app/Contents/Frameworks/rime-plugins"
echo "Installing into: $PLUGIN_DIR"
echo "You may be prompted for your Mac password."
sudo cp "$SRC" "$PLUGIN_DIR/librime-qjs.dylib"
sudo chmod 755 "$PLUGIN_DIR/librime-qjs.dylib"
sudo codesign --force --sign - "$PLUGIN_DIR/librime-qjs.dylib" || true
ls -la "$PLUGIN_DIR/librime-qjs.dylib"

# Also refresh user-level Squirrel-qjs copy
USER_APP="$HOME/Library/Input Methods/Squirrel-qjs.app"
if [[ -d "$USER_APP" ]]; then
  cp "$SRC" "$USER_APP/Contents/Frameworks/rime-plugins/librime-qjs.dylib"
  codesign --force --deep --sign - "$USER_APP" || true
fi

# User JS assets (prefer sync_rime.sh for a full deploy)
mkdir -p "$HOME/Library/Rime/js"
cp -f "$ROOT/rime/js/gujarati_translator.js" "$HOME/Library/Rime/js/" 2>/dev/null || true
cp -f "$ROOT/rime/js/gu_lexicon_blob.json" "$HOME/Library/Rime/js/" 2>/dev/null || \
  cp -f "$ROOT/rime/gu_lexicon_blob.json" "$HOME/Library/Rime/js/" 2>/dev/null || true
cp -f "$ROOT/rime/gujarati.schema.yaml" "$HOME/Library/Rime/" 2>/dev/null || true
cp -f "$ROOT/vendor/librime-qjs/qjs" "$HOME/Library/Rime/js/qjs" 2>/dev/null || true
chmod +x "$HOME/Library/Rime/js/qjs" 2>/dev/null || true

killall Squirrel 2>/dev/null || true
sleep 1
open "/Library/Input Methods/Squirrel.app" 2>/dev/null || true
echo
echo "Done. Check:  grep qjs \$TMPDIR/rime.squirrel/rime.squirrel.INFO"
echo "Then Deploy in Squirrel and type with Gujarati schema."
