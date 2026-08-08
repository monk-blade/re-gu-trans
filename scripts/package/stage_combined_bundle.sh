#!/usr/bin/env bash
# Stage one self-contained core + optional model installer bundle.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLATFORM="${1:?platform: linux|macos|windows}"
CORE_DIR="${2:?directory containing the built core package/payload}"
MODEL_DIR="${3:?validated model-pack directory}"
OUT="${4:?bundle staging directory}"
VERSION="${5:?release version}"

case "$PLATFORM" in
  linux) INSTALLER="linux/install_bundle.sh" ;;
  macos) INSTALLER="macos/install_bundle.sh" ;;
  windows) INSTALLER="windows/install_bundle.ps1" ;;
  *) echo "FAIL: unsupported platform $PLATFORM" >&2; exit 2 ;;
esac

test -d "$MODEL_DIR" || { echo "FAIL: model directory missing: $MODEL_DIR" >&2; exit 1; }
test -f "$MODEL_DIR/SHA256SUMS" || { echo "FAIL: model SHA256SUMS missing" >&2; exit 1; }
test -f "$MODEL_DIR/training-manifest.json" || { echo "FAIL: model training manifest missing" >&2; exit 1; }
test -f "$ROOT/scripts/package/$INSTALLER" || { echo "FAIL: bundle installer missing" >&2; exit 1; }

MODEL_VERSION="$(python3 - "$MODEL_DIR/training-manifest.json" <<'PY'
import json, sys
manifest = json.load(open(sys.argv[1], encoding='utf-8'))
version = manifest.get('model_version')
if version != 'gu-transformer-ctc-v3':
    raise SystemExit('FAIL: combined bundle model version is not gu-transformer-ctc-v3')
print(version)
PY
)"

rm -rf "$OUT"
mkdir -p "$OUT/core" "$OUT/model"
cp -R "$MODEL_DIR/." "$OUT/model/"

if [[ "$PLATFORM" == "windows" ]]; then
  cp -R "$CORE_DIR/payload" "$OUT/"
  cp -R "$CORE_DIR/plugin" "$OUT/"
else
  found=0
  for package in "$CORE_DIR"/*.deb "$CORE_DIR"/*.rpm "$CORE_DIR"/*.pkg; do
    [[ -f "$package" ]] || continue
    cp -f "$package" "$OUT/core/"
    found=1
  done
  test "$found" = 1 || { echo "FAIL: no native core package found in $CORE_DIR" >&2; exit 1; }
fi

cp -f "$ROOT/scripts/package/$INSTALLER" "$OUT/$(basename "$INSTALLER")"
chmod +x "$OUT/$(basename "$INSTALLER")" 2>/dev/null || true
cat > "$OUT/README.txt" <<EOF
re-gu-trans ${VERSION} combined ${PLATFORM} bundle

The installer verifies every file before changing the system, installs the
deterministic core and verified offline model, preserves Rime user data, and
reloads the detected frontend. Use --core-only to skip the model or
--verify-only to validate without installing.
EOF

python3 - "$OUT" "$PLATFORM" "$VERSION" "$MODEL_VERSION" <<'PY'
from hashlib import sha256
from pathlib import Path
import json, sys

root = Path(sys.argv[1])
platform = sys.argv[2]
version = sys.argv[3]
files = {}
for path in sorted(item for item in root.rglob('*') if item.is_file() and item.name != 'bundle-manifest.json'):
    files[path.relative_to(root).as_posix()] = sha256(path.read_bytes()).hexdigest()
manifest = {
    'version': 1,
    'release_version': version,
    'platform': platform,
    'core': 'core/' if platform != 'windows' else 'payload/ + plugin/',
    'model_dir': 'model/',
    'model_version': sys.argv[4],
    'runtime_model_dir': 'gujarati-model',
    'install_model_by_default': True,
    'files': files,
}
(root / 'bundle-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
PY
echo "COMBINED_BUNDLE_STAGED platform=$PLATFORM out=$OUT files=$(find "$OUT" -type f | wc -l)"
