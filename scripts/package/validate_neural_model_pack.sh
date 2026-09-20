#!/usr/bin/env bash
# Validate an extracted optional Gujarati model pack.
set -euo pipefail
PACK="${1:?extracted model-pack directory}"
test -d "$PACK" || { echo "FAIL: model pack directory missing: $PACK" >&2; exit 1; }

if [ -f "$PACK/indicxlit_encoder.onnx" ]; then
  MODEL_FILES=(indicxlit_encoder.onnx indicxlit_decoder_v2.onnx)
else
  MODEL_FILES=(gujarati_xlit.int8.onnx vocab.tsv)
fi
for file in \
  "${MODEL_FILES[@]}" vocab.json model-card.md \
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
known_versions = {
    'gu-transformer-ctc-v3': {'model_files': ['gujarati_xlit.int8.onnx'], 'warm_p95_budget_ms': 10},
    'gu-transformer-ctc-v4': {'model_files': ['gujarati_xlit.int8.onnx'], 'warm_p95_budget_ms': 10},
    'indicxlit-fairseq-v1.0': {
        'model_files': ['indicxlit_encoder.onnx', 'indicxlit_decoder_v2.onnx'],
        # Autoregressive beam search over a seq2seq transformer is inherently
        # slower than the single-pass CTC model this replaces (~25ms vs ~2ms
        # warm p50, measured in eval/indicxlit_ab_summary.json); the budget
        # here reflects that accepted tradeoff, not an unoptimized regression.
        # Set generously (measured ~46ms warm p95 on a 28-core workstation,
        # ~117ms on a shared 2-vCPU GitHub Actions runner) so it still catches
        # a true regression (e.g. beam search failing to stop early,
        # previously ~400ms) without flaking on cross-machine CPU variance.
        'warm_p95_budget_ms': 150,
    },
}
version = manifest.get('model_version')
if version not in known_versions:
    raise SystemExit('FAIL: unexpected model version')
spec = known_versions[version]
if not manifest.get('benchmark_family_exclusion'):
    raise SystemExit('FAIL: benchmark-family exclusion evidence missing')
metrics = manifest.get('metrics') or {}
runtime = manifest.get('runtime') or {}
if any(metrics.get(k) is None for k in ('top1_pct', 'top3_pct', 'recall_at_6_pct')):
    raise SystemExit('FAIL: model metrics are incomplete')
if runtime.get('warm_p95_ms') is None or runtime['warm_p95_ms'] > spec['warm_p95_budget_ms']:
    raise SystemExit('FAIL: model runtime evidence is missing or over budget')
model_sha256 = manifest.get('model_sha256') or {}
if isinstance(model_sha256, str):
    model_sha256 = {spec['model_files'][0]: model_sha256}
for name in spec['model_files']:
    if sha256((root / name).read_bytes()).hexdigest() != model_sha256.get(name):
        raise SystemExit(f'FAIL: model checksum differs from training manifest: {name}')
if sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) > 45 * 1024 * 1024:
    raise SystemExit('FAIL: model pack exceeds 45 MB')
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
