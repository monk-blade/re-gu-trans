#!/usr/bin/env bash
# Sync re-gu-trans Rime package into the local Rime user dir and reload.
# qjs-only: no table .dict.yaml / apple table. Assets under js/; plugins also
# copied to user-dir root so @gujarati_translator resolves.
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
mkdir -p "$RIME" "$RIME/run" "$RIME/js" "$RIME/js/lm"
ALLOW_TEXT_FALLBACK="${ALLOW_TEXT_FALLBACK:-0}"

JS="$ROOT/rime/js"
require() { [[ -f "$1" ]] || { echo "ERROR: missing $1" >&2; exit 1; }; }

require "$ROOT/rime/gujarati.schema.yaml"
require "$JS/gujarati_translator.js"
require "$JS/commit_on_punct_processor.js"
require "$JS/ranking_policy.json"
if [[ ! -f "$JS/lexicon.trie.bin" && ! -f "$JS/gu_lexicon_blob.json" ]]; then
  echo "ERROR: need lexicon.trie.bin or gu_lexicon_blob.json" >&2
  exit 1
fi

cp -f "$ROOT/rime/gujarati.schema.yaml" "$RIME/"
cp -f "$ROOT/rime/gujarati.custom.yaml.sample" "$RIME/" 2>/dev/null || true

# Modules + policy
cp -f "$JS/gujarati_translator.js" "$RIME/js/"
cp -f "$JS/engine.js" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/ranking_primitives.js" "$RIME/js/"
cp -f "$JS/commit_on_punct_processor.js" "$RIME/js/"
cp -f "$JS/selection_tracker_processor.js" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/ranking.js" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/phonetic.js" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/storage.js" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/learning.js" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/neural.js" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/runtime_capabilities.js" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/ranking_policy.json" "$RIME/js/"
cp -f "$JS/emoji_keywords.json" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/exceptions.json" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/ltr_coefficients.json" "$RIME/js/" 2>/dev/null || true
cp -f "$JS/native_lm_meta.json" "$RIME/js/"
cp -f "$JS/"*.trie.bin "$RIME/js/" 2>/dev/null || true
# Explicit development fallback only. Default sync mirrors release binary mode.
if [[ "$ALLOW_TEXT_FALLBACK" == "1" ]]; then
  cp -f "$JS/gu_lexicon_blob.json" "$RIME/js/" 2>/dev/null || true
  cp -f "$JS/prefix.trie.txt" "$RIME/js/" 2>/dev/null || true
  cp -f "$JS/lm/"*.tsv "$RIME/js/lm/" 2>/dev/null || true
  cp -f "$JS/lm/"*.json "$RIME/js/lm/" 2>/dev/null || true
else
  rm -f "$RIME/js/gu_lexicon_blob.json"
  rm -f "$RIME/js/prefix.trie.txt"
  rm -f "$RIME/js/lm/unigram.tsv" "$RIME/js/lm/stems.json" "$RIME/js/lm/attested.json"
fi

# qjs plugins: filename at user-dir root (schema @name) + mirror under js/
cp -f "$JS/gujarati_translator.js" "$RIME/gujarati_translator.js"
cp -f "$JS/commit_on_punct_processor.js" "$RIME/commit_on_punct_processor.js"

# Enable schema without appending a second patch: block (merge helper)
DEFAULT_CUSTOM="$RIME/default.custom.yaml"
if [[ ! -f "$DEFAULT_CUSTOM" ]]; then
  cat > "$DEFAULT_CUSTOM" <<'EOF'
patch:
  schema_list:
    - schema: gujarati
EOF
elif ! grep -q 'schema: gujarati' "$DEFAULT_CUSTOM" 2>/dev/null; then
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$DEFAULT_CUSTOM" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
if "schema: gujarati" in text:
    raise SystemExit(0)
# Insert under existing schema_list if present; else create one patch block
if "schema_list:" in text:
    lines = text.splitlines(True)
    out = []
    inserted = False
    for i, line in enumerate(lines):
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
  else
    echo "NOTE: add '- schema: gujarati' under patch.schema_list in $DEFAULT_CUSTOM"
  fi
fi

if [[ -x "/Library/Input Methods/Squirrel.app/Contents/MacOS/Squirrel" ]]; then
  "/Library/Input Methods/Squirrel.app/Contents/MacOS/Squirrel" --reload || true
elif command -v fcitx5-remote >/dev/null 2>&1; then
  fcitx5-remote -r || true
elif command -v ibus >/dev/null 2>&1; then
  ibus restart || true
fi

echo "Synced to $RIME (qjs-only; no table dict)"
echo "Engine: exact → dict → phonetic → latin → prefix → emoji"
echo "Try: jamin, favshe, parkhavyu, mne, prem — then Space or ."
