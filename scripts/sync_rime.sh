#!/usr/bin/env bash
# Sync re-gu-trans Rime package into the local Rime user dir and reload.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

detect_rime_dir() {
  if [[ -n "${RIME_USER_DIR:-}" ]]; then
    echo "$RIME_USER_DIR"
    return
  fi
  case "$(uname -s)" in
    Darwin)
      echo "${HOME}/Library/Rime"
      ;;
    Linux)
      if [[ -d "${HOME}/.local/share/fcitx5/rime" ]] || command -v fcitx5 >/dev/null 2>&1; then
        echo "${HOME}/.local/share/fcitx5/rime"
      elif [[ -d "${HOME}/.config/ibus/rime" ]] || command -v ibus >/dev/null 2>&1; then
        echo "${HOME}/.config/ibus/rime"
      else
        echo "${HOME}/.local/share/fcitx5/rime"
      fi
      ;;
    *)
      echo "${HOME}/.config/ibus/rime"
      ;;
  esac
}

RIME="$(detect_rime_dir)"
mkdir -p "$RIME" "$RIME/run" "$RIME/js" "$RIME/js/lm" "$RIME/lm"

cp -f "$ROOT/rime/gujarati.schema.yaml" "$RIME/"
cp -f "$ROOT/rime/gujarati.dict.yaml" "$RIME/"
cp -f "$ROOT/rime/gujarati_apple.dict.yaml" "$RIME/"
cp -f "$ROOT/rime/gujarati_translator.js" "$RIME/" 2>/dev/null || true
cp -f "$ROOT/rime/gujarati_translator.js" "$RIME/js/" 2>/dev/null || true
cp -f "$ROOT/rime/commit_on_punct_processor.js" "$RIME/js/" 2>/dev/null || true
cp -f "$ROOT/rime/gujarati.custom.yaml.sample" "$RIME/" 2>/dev/null || true
cp -f "$ROOT/rime/gu_lexicon_blob.json" "$RIME/" 2>/dev/null || true
cp -f "$ROOT/rime/gu_lexicon_blob.json" "$RIME/js/" 2>/dev/null || true
cp -f "$ROOT/rime/js/emoji_keywords.json" "$RIME/js/" 2>/dev/null || true

if [[ -d "$ROOT/rime/js/lm" ]]; then
  cp -f "$ROOT/rime/js/lm/"*.tsv "$RIME/js/lm/" 2>/dev/null || true
  cp -f "$ROOT/rime/js/lm/"*.json "$RIME/js/lm/" 2>/dev/null || true
  cp -f "$ROOT/rime/js/lm/"*.tsv "$RIME/lm/" 2>/dev/null || true
  cp -f "$ROOT/rime/js/lm/"*.json "$RIME/lm/" 2>/dev/null || true
fi
if [[ -d "$ROOT/rime/lm" ]]; then
  cp -f "$ROOT/rime/lm/"* "$RIME/lm/" 2>/dev/null || true
fi

# Ensure schema is enabled
DEFAULT_CUSTOM="$RIME/default.custom.yaml"
if [[ ! -f "$DEFAULT_CUSTOM" ]]; then
  cat > "$DEFAULT_CUSTOM" <<'EOF'
patch:
  schema_list:
    - schema: gujarati
EOF
elif ! grep -q 'schema: gujarati' "$DEFAULT_CUSTOM" 2>/dev/null; then
  echo "NOTE: add '- schema: gujarati' under patch.schema_list in $DEFAULT_CUSTOM"
fi

# Ranker helper wrapper (native binary when present; else python)
mkdir -p "$RIME/run"
if [[ -x "$ROOT/tools/gu_ranker_client_fast" ]]; then
  cat > "$RIME/run/gu_ranker_client" << EOF
#!/bin/bash
exec "$ROOT/tools/gu_ranker_client_fast" "\$@"
EOF
elif [[ -x "$ROOT/tools/gu_ranker_client" ]]; then
  cat > "$RIME/run/gu_ranker_client" << EOF
#!/bin/bash
exec "$ROOT/tools/gu_ranker_client" "\$@"
EOF
else
  cat > "$RIME/run/gu_ranker_client" << EOF
#!/bin/bash
exec python3 "$ROOT/runtime/onnx_ranker/client.py" "\$@"
EOF
fi
chmod +x "$RIME/run/gu_ranker_client"

# Reload frontend if available
if [[ -x "/Library/Input Methods/Squirrel.app/Contents/MacOS/Squirrel" ]]; then
  "/Library/Input Methods/Squirrel.app/Contents/MacOS/Squirrel" --reload || true
elif command -v fcitx5-remote >/dev/null 2>&1; then
  fcitx5-remote -r || true
elif command -v ibus >/dev/null 2>&1; then
  ibus restart || true
fi

echo "Synced to $RIME"
echo "Engine: exact → dict-phonetic → latin → phonetic → prefix → emoji"
echo "Commit: Space and . , ; ' etc. (processor before key_binder)"
echo "Try: jamin, favshe, prem (😍 below પ્રેમ), smile — then Space or ."
