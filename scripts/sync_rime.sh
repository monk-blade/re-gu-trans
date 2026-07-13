#!/usr/bin/env bash
# Sync re-gu-trans Rime package into ~/Library/Rime and deploy.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RIME="${HOME}/Library/Rime"
mkdir -p "$RIME" "$RIME/run" "$RIME/js" "$RIME/js/lm" "$RIME/lm"

cp -f "$ROOT/rime/gujarati.schema.yaml" "$RIME/"
cp -f "$ROOT/rime/gujarati.dict.yaml" "$RIME/"
cp -f "$ROOT/rime/gujarati_apple.dict.yaml" "$RIME/"
cp -f "$ROOT/rime/gujarati_translator.js" "$RIME/" 2>/dev/null || true
cp -f "$ROOT/rime/gujarati_translator.js" "$RIME/js/" 2>/dev/null || true
cp -f "$ROOT/rime/commit_on_punct_processor.js" "$RIME/js/" 2>/dev/null || true
cp -f "$ROOT/rime/gu_lexicon_blob.json" "$RIME/" 2>/dev/null || true
cp -f "$ROOT/rime/gu_lexicon_blob.json" "$RIME/js/" 2>/dev/null || true

# Native word frequency + stems for dictionary rescoring (macOS / IndicXlit style)
if [[ -d "$ROOT/rime/js/lm" ]]; then
  cp -f "$ROOT/rime/js/lm/"*.tsv "$RIME/js/lm/" 2>/dev/null || true
  cp -f "$ROOT/rime/js/lm/"*.json "$RIME/js/lm/" 2>/dev/null || true
  cp -f "$ROOT/rime/js/lm/"*.tsv "$RIME/lm/" 2>/dev/null || true
  cp -f "$ROOT/rime/js/lm/"*.json "$RIME/lm/" 2>/dev/null || true
fi
if [[ -d "$ROOT/rime/lm" ]]; then
  cp -f "$ROOT/rime/lm/"* "$RIME/lm/" 2>/dev/null || true
fi

cat > "$RIME/run/gu_ranker_client" << EOF
#!/bin/bash
exec "$ROOT/tools/gu_ranker_client" "\$@"
EOF
chmod +x "$RIME/run/gu_ranker_client"

if [[ -x "$ROOT/tools/gu_ranker_client_fast" ]]; then
  ln -sfn "$ROOT/tools/gu_ranker_client_fast" "$RIME/run/gu_ranker_client_fast"
fi

SQUIRREL="/Library/Input Methods/Squirrel.app/Contents/MacOS/Squirrel"
if [[ -x "$SQUIRREL" ]]; then
  "$SQUIRREL" --reload || true
fi

echo "Synced to $RIME"
echo "Engine: lexicon exact → dict-validated phonetic → latin → phonetic → prefix"
echo "Try: jamin (જમીન), favshe (ફાવશે), kem, aavjo"
