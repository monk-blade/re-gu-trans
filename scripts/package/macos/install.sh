#!/usr/bin/env bash
# Manual / zip installer for macOS (Apple Silicon).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DYLIB="$ROOT/plugin/librime-qjs.dylib"
PAYLOAD="$ROOT/payload/rime"
PLUGIN_DIR="/Library/Input Methods/Squirrel.app/Contents/Frameworks/rime-plugins"
SQUIRREL="/Library/Input Methods/Squirrel.app"
BACKUP_DIR="${TMPDIR:-/tmp}/re-gu-trans-plugin-backup-$$"

if [[ ! -d "$SQUIRREL" ]]; then
  echo "ERROR: Squirrel not installed at $SQUIRREL" >&2
  echo "Download: https://github.com/rime/squirrel/releases" >&2
  exit 1
fi
if [[ ! -f "$DYLIB" ]]; then
  echo "ERROR: missing $DYLIB" >&2
  exit 1
fi

echo "Installing librime-qjs.dylib (admin) with rollback backup..."
sudo mkdir -p "$PLUGIN_DIR" "$BACKUP_DIR"
if [[ -f "$PLUGIN_DIR/librime-qjs.dylib" ]]; then
  sudo cp -f "$PLUGIN_DIR/librime-qjs.dylib" "$BACKUP_DIR/librime-qjs.dylib"
fi
if ! sudo cp -f "$DYLIB" "$PLUGIN_DIR/librime-qjs.dylib"; then
  echo "ERROR: plugin install failed; restoring backup if present" >&2
  if [[ -f "$BACKUP_DIR/librime-qjs.dylib" ]]; then
    sudo cp -f "$BACKUP_DIR/librime-qjs.dylib" "$PLUGIN_DIR/librime-qjs.dylib" || true
  fi
  exit 1
fi
sudo chmod 755 "$PLUGIN_DIR/librime-qjs.dylib"
sudo codesign --force --sign - "$PLUGIN_DIR/librime-qjs.dylib" || true

RIME="${HOME}/Library/Rime"
mkdir -p "$RIME/js" "$RIME/run"
cp -f "$PAYLOAD/gujarati.schema.yaml" "$RIME/"
# Generic staged tree: modules, small JSON, binary Tries (blob/LM only if present)
cp -f "$PAYLOAD/js/"*.js "$RIME/js/" 2>/dev/null || true
cp -f "$PAYLOAD/js/"*.json "$RIME/js/" 2>/dev/null || true
cp -f "$PAYLOAD/js/"*.bin "$RIME/js/" 2>/dev/null || true
if [[ -d "$PAYLOAD/js/lm" ]]; then
  mkdir -p "$RIME/js/lm"
  cp -f "$PAYLOAD/js/lm/"* "$RIME/js/lm/" 2>/dev/null || true
fi
# qjs resolves @plugin from user-dir root
cp -f "$PAYLOAD/js/gujarati_translator.js" "$RIME/"
cp -f "$PAYLOAD/js/commit_on_punct_processor.js" "$RIME/"

# Prefer deployer when available; else merge schema_list safely (no second patch block)
if command -v rime_deployer >/dev/null 2>&1; then
  rime_deployer --add-schema gujarati 2>/dev/null || true
fi
CUSTOM="$RIME/default.custom.yaml"
# shellcheck source=/dev/null
if [[ -f "$ROOT/../../common.sh" ]]; then
  # packaged tree may not include common.sh; inline ensure
  :
fi
python3 - "$CUSTOM" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.exists():
    p.write_text("patch:\n  schema_list:\n    - schema: gujarati\n", encoding="utf-8")
    raise SystemExit(0)
text = p.read_text(encoding="utf-8")
if "schema: gujarati" in text:
    raise SystemExit(0)
if "schema_list:" in text:
    lines = text.splitlines(True)
    out = []
    inserted = False
    for line in lines:
        out.append(line)
        if (not inserted) and line.strip() == "schema_list:":
            indent = line[: len(line) - len(line.lstrip())]
            out.append(f"{indent}  - schema: gujarati\n")
            inserted = True
    if not inserted:
        out.append("\npatch:\n  schema_list:\n    - schema: gujarati\n")
    p.write_text("".join(out), encoding="utf-8")
else:
    p.write_text(text.rstrip() + "\n\npatch:\n  schema_list:\n    - schema: gujarati\n", encoding="utf-8")
PY

"$SQUIRREL/Contents/MacOS/Squirrel" --reload 2>/dev/null || true
echo "Done. Select Squirrel → Gujarati and Deploy if needed."
echo "Plugin backup (if any): $BACKUP_DIR"
