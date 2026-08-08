#!/usr/bin/env bash
# Install a self-contained Linux core + model bundle.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -f "$SCRIPT_DIR/bundle-manifest.json" ]]; then ROOT="$SCRIPT_DIR"; else ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"; fi
CORE_ONLY=0
VERIFY_ONLY=0
NO_RELOAD=0
USER_DIR=""
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
if manifest.get('platform') != 'linux' or manifest.get('model_version') != 'gu-transformer-ctc-v3':
    raise SystemExit('bundle platform/model version mismatch')
for name, expected in (manifest.get('files') or {}).items():
    path = root / name
    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f'checksum mismatch: {name}')
print('BUNDLE_VERIFY_OK')
PY
[[ "$VERIFY_ONLY" == 1 ]] && exit 0

if [[ -z "$USER_DIR" ]]; then
  if [[ -d "$HOME/.local/share/fcitx5/rime" ]] || command -v fcitx5 >/dev/null 2>&1; then
    USER_DIR="$HOME/.local/share/fcitx5/rime"
  else
    USER_DIR="$HOME/.config/ibus/rime"
  fi
fi

if command -v dnf >/dev/null 2>&1; then
  package=("$ROOT"/core/*.rpm)
  sudo dnf install -y "${package[0]}"
elif command -v apt-get >/dev/null 2>&1; then
  package=("$ROOT"/core/*.deb)
  sudo apt-get install -y "${package[0]}"
elif command -v rpm >/dev/null 2>&1; then
  package=("$ROOT"/core/*.rpm)
  sudo rpm -U --replacepkgs "${package[0]}"
else
  echo "ERROR: no dnf, apt-get, or rpm package installer found" >&2
  exit 1
fi

if command -v re-gu-trans-enable >/dev/null 2>&1; then
  RIME_USER_DIR="$USER_DIR" re-gu-trans-enable
else
  echo "ERROR: core package did not install re-gu-trans-enable" >&2
  exit 1
fi

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
  temp="$(mktemp -d "$USER_DIR/.gujarati-model-install.XXXXXX")"
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

if [[ "$NO_RELOAD" == 0 ]]; then
  command -v fcitx5-remote >/dev/null 2>&1 && fcitx5-remote -r || true
  command -v ibus >/dev/null 2>&1 && ibus restart || true
fi
echo "Done. Select Gujarati Transliteration in your Rime frontend."
