#!/usr/bin/env bash
# Stage an optional, real neural model pack. Placeholders and null reports fail.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="${1:?model artifact directory}"
OUT="${2:-$ROOT/dist/neural-model-pack}"

# The seq2seq (IndicXlit) architecture ships two ONNX graphs and no vocab.tsv;
# the single-pass CTC architecture ships one graph plus a vocab.tsv. Detect
# which one this source directory holds so both remain stageable.
if [ -f "$SOURCE/indicxlit_encoder.onnx" ]; then
  MODEL_FILES=("$SOURCE/indicxlit_encoder.onnx" "$SOURCE/indicxlit_decoder_v2.onnx")
else
  MODEL_FILES=("$SOURCE/gujarati_xlit.int8.onnx" "$SOURCE/vocab.tsv")
fi
PLUGIN="${NEURAL_PLUGIN:-$SOURCE/librime-gujarati-model}"
ORT_RUNTIME="${ONNXRUNTIME_LIBRARY:-$SOURCE/libonnxruntime}"
CARD="$SOURCE/model-card.md"
MANIFEST="$SOURCE/training-manifest.json"
VOCAB_JSON="$SOURCE/vocab.json"

for file in "${MODEL_FILES[@]}" "$PLUGIN" "$ORT_RUNTIME" "$CARD" "$MANIFEST" "$VOCAB_JSON"; do
  test -f "$file" || { echo "FAIL: missing model-pack artifact: $file" >&2; exit 1; }
done
python3 - "$MANIFEST" <<'PY'
import json, sys
p=json.load(open(sys.argv[1], encoding='utf-8'))
required=[p.get('model_version'), (p.get('metrics') or {}).get('top1_pct'), (p.get('metrics') or {}).get('recall_at_6_pct'), (p.get('runtime') or {}).get('warm_p95_ms')]
if any(v is None for v in required):
    raise SystemExit('FAIL: training manifest contains null release evidence')
PY

rm -rf "$OUT"
mkdir -p "$OUT/LICENSES"
for file in "${MODEL_FILES[@]}"; do cp -f "$file" "$OUT/"; done
cp -f "$PLUGIN" "$OUT/"
cp -f "$ORT_RUNTIME" "$OUT/"
cp -f "$VOCAB_JSON" "$OUT/"
cp -f "$CARD" "$OUT/model-card.md"
cp -f "$MANIFEST" "$OUT/training-manifest.json"
cp -R "$SOURCE/LICENSES/." "$OUT/LICENSES/"

BYTES=$(find "$OUT" -type f -exec wc -c {} + | awk 'END {print $1}')
# The seq2seq IndicXlit pair (~14MB int8) plus the ONNX Runtime shared
# library (~22MB, unchanged from the CTC pack) puts a full pack just over
# the previous 35MB CTC-only budget; raised with headroom rather than
# shaving it razor-thin against one runtime build.
MAX=$((45 * 1024 * 1024))
test "$BYTES" -le "$MAX" || { echo "FAIL: model pack exceeds 45MB: $BYTES" >&2; exit 1; }
python3 - "$OUT" <<'PY'
from hashlib import sha256
from pathlib import Path
import sys
root = Path(sys.argv[1])
lines = []
for path in sorted(item for item in root.rglob('*') if item.is_file() and item.name != 'SHA256SUMS'):
    lines.append(f"{sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root).as_posix()}")
(root / 'SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')
PY
echo "staged neural model pack: $OUT bytes=$BYTES"
