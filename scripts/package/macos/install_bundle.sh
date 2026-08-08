#!/usr/bin/env bash
# Install a self-contained macOS arm64 core + model bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
CORE_ONLY=0
VERIFY_ONLY=0
NO_RELOAD=0
USER_DIR="${HOME}/Library/Rime"
usage() { echo "usage: install_bundle.sh [--core-only] [--verify-only] [--user-dir PATH] [--no-reload]"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --core-only) CORE_ONLY=1; shift ;;
    --verify-only) VERIFY_ONLY=1; shift ;;
    --no-reload) NO_RELOAD=1; shift ;;
    --user-dir) USER_DIR="${2:?--user-dir needs PATH}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

python3 - "$ROOT" <<'PY'
from hashlib import sha256
from pathlib import Path
import json, sys
root = Path(sys.argv[1])
manifest = json.loads((root / 'bundle-manifest.json').read_text(encoding='utf-8'))
if manifest.get('platform') != 'macos' or manifest.get('model_version') != 'gu-transformer-ctc-v3':
    raise SystemExit('bundle platform/model version mismatch')
for name, expected in (manifest.get('files') or {}).items():
    path = root / name
    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f'checksum mismatch: {name}')
print('BUNDLE_VERIFY_OK')
PY
[[ "$VERIFY_ONLY" == 1 ]] && exit 0

package=("$ROOT"/core/*.pkg)
sudo installer -pkg "${package[0]}" -target /

if [[ "$CORE_ONLY" == 0 ]]; then
  mkdir -p "$USER_DIR"
  temp=""
  previous=""
  destination="$USER_DIR/gujarati-model"
  rollback_model() {
    [[ -n "$temp" && -e "$temp" ]] && rm -rf "$temp"
    if [[ -n "$previous" && -e "$previous" && ! -e "$destination" ]]; then
      mv "$previous" "$destination" || true
    fi
  }
  trap rollback_model EXIT
  temp="$(mktemp -d "${TMPDIR:-/tmp}/gujarati-model-install.XXXXXX")"
  cp -a "$ROOT/model/." "$temp/"
  if [[ -e "$destination" ]]; then
    previous="$USER_DIR/gujarati-model.previous.$(date +%Y%m%d%H%M%S).$$"
    mv "$destination" "$previous"
  fi
  mv "$temp" "$destination"
  temp=""
  trap - EXIT
  echo "Installed verified model at $destination"
fi

if [[ "$NO_RELOAD" == 0 && -x "/Library/Input Methods/Squirrel.app/Contents/MacOS/Squirrel" ]]; then
  "/Library/Input Methods/Squirrel.app/Contents/MacOS/Squirrel" --reload || true
fi
echo "Done. Select Gujarati in Squirrel and Deploy if needed."
