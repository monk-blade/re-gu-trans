#!/usr/bin/env bash
# Stage an optional, real neural model pack. Placeholders and null reports fail.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE="${1:?model artifact directory}"
OUT="${2:-$ROOT/dist/neural-model-pack}"

MODEL="$SOURCE/gujarati_xlit.int8.onnx"
PLUGIN="${NEURAL_PLUGIN:-$SOURCE/librime-gujarati-model}"
ORT_RUNTIME="${ONNXRUNTIME_LIBRARY:-$SOURCE/libonnxruntime}"
CARD="$SOURCE/model-card.md"
MANIFEST="$SOURCE/training-manifest.json"
VOCAB_JSON="$SOURCE/vocab.json"
VOCAB_TSV="$SOURCE/vocab.tsv"

for file in "$MODEL" "$PLUGIN" "$ORT_RUNTIME" "$CARD" "$MANIFEST" "$VOCAB_JSON" "$VOCAB_TSV"; do
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
cp -f "$MODEL" "$OUT/"
cp -f "$PLUGIN" "$OUT/"
cp -f "$ORT_RUNTIME" "$OUT/"
cp -f "$VOCAB_JSON" "$OUT/"
cp -f "$VOCAB_TSV" "$OUT/"
cp -f "$CARD" "$OUT/model-card.md"
cp -f "$MANIFEST" "$OUT/training-manifest.json"
cp -R "$SOURCE/LICENSES/." "$OUT/LICENSES/"

BYTES=$(find "$OUT" -type f -exec wc -c {} + | awk 'END {print $1}')
MAX=$((35 * 1024 * 1024))
test "$BYTES" -le "$MAX" || { echo "FAIL: model pack exceeds 35MB: $BYTES" >&2; exit 1; }
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
