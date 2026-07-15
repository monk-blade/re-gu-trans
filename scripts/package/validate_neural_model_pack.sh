#!/usr/bin/env bash
# Validate an extracted optional Gujarati model pack.
set -euo pipefail
PACK="${1:?extracted model-pack directory}"
test -d "$PACK" || { echo "FAIL: model pack directory missing: $PACK" >&2; exit 1; }

for file in \
  gujarati_xlit.int8.onnx vocab.json vocab.tsv model-card.md \
  training-manifest.json SHA256SUMS LICENSES/NOTICE.md; do
  test -f "$PACK/$file" || { echo "FAIL: model pack lacks $file" >&2; exit 1; }
done
PLUGIN="$(find "$PACK" -maxdepth 1 -type f \( \
  -name 'librime-gujarati-model.dylib' -o \
  -name 'librime-gujarati-model.so' -o \
  -name 'rime-gujarati-model.dll' \) | head -1 || true)"
test -n "$PLUGIN" || { echo "FAIL: native Gujarati model plugin missing" >&2; exit 1; }
RUNTIME="$(find "$PACK" -maxdepth 1 -type f \( \
  -name 'libonnxruntime.dylib' -o \
  -name 'libonnxruntime.so*' -o \
  -name 'onnxruntime.dll' \) | head -1 || true)"
test -n "$RUNTIME" || { echo "FAIL: ONNX Runtime library missing" >&2; exit 1; }

python3 - "$PACK" <<'PY'
from hashlib import sha256
from pathlib import Path
import json, sys
root = Path(sys.argv[1])
manifest = json.loads((root / 'training-manifest.json').read_text(encoding='utf-8'))
if manifest.get('model_version') != 'gu-transformer-ctc-v2':
    raise SystemExit('FAIL: unexpected model version')
if not manifest.get('benchmark_family_exclusion'):
    raise SystemExit('FAIL: benchmark-family exclusion evidence missing')
metrics = manifest.get('metrics') or {}
runtime = manifest.get('runtime') or {}
if any(metrics.get(k) is None for k in ('top1_pct', 'top3_pct', 'recall_at_6_pct')):
    raise SystemExit('FAIL: model metrics are incomplete')
if runtime.get('warm_p95_ms') is None or runtime['warm_p95_ms'] > 10:
    raise SystemExit('FAIL: model runtime evidence is missing or over budget')
if sha256((root / 'gujarati_xlit.int8.onnx').read_bytes()).hexdigest() != manifest.get('model_sha256'):
    raise SystemExit('FAIL: model checksum differs from training manifest')
if sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) > 35 * 1024 * 1024:
    raise SystemExit('FAIL: model pack exceeds 35 MB')
expected = {}
for line in (root / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
    digest, name = line.split('  ', 1)
    expected[name] = digest
for name, digest in expected.items():
    path = root / name
    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != digest:
        raise SystemExit(f'FAIL: checksum mismatch: {name}')
PY
echo "VALIDATE_NEURAL_MODEL_PACK_OK pack=$PACK plugin=$(basename "$PLUGIN")"
