#!/usr/bin/env bash
# Install librime-qjs into system Squirrel (requires admin + Terminal Full Disk Access)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/dist/plugins/librime-qjs.dylib"
if [[ ! -f "$SRC" ]]; then SRC="$ROOT/vendor/librime-qjs/librime-qjs.dylib"; fi
if [[ ! -f "$SRC" ]] || ! grep -a -q writeFileAtomic "$SRC"; then
  echo "Building required patched librime-qjs with writeFileAtomic..."
  OUT_DYLIB="$ROOT/dist/plugins/librime-qjs.dylib" \
    "$ROOT/scripts/package/macos/build_librime_qjs.sh"
  SRC="$ROOT/dist/plugins/librime-qjs.dylib"
fi
"$ROOT/scripts/package/verify_qjs_plugin.sh" "$SRC"

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

# User assets use the same binary-only deployment contract as packages.
"$ROOT/scripts/sync_rime.sh"

killall Squirrel 2>/dev/null || true
sleep 1
open "/Library/Input Methods/Squirrel.app" 2>/dev/null || true
echo
echo "Done. Check:  grep qjs \$TMPDIR/rime.squirrel/rime.squirrel.INFO"
echo "Then Deploy in Squirrel and type with Gujarati schema."
