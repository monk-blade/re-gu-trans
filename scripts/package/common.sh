#!/usr/bin/env bash
# Shared helpers for packaging scripts.
# shellcheck disable=SC2034

set -euo pipefail

PACKAGE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PACKAGE_ROOT

# Pin: HuangJian/librime-qjs v1.3.0 → librime 1.16.1
LIBRIME_QJS_TAG="${LIBRIME_QJS_TAG:-v1.3.0}"
LIBRIME_TAG="${LIBRIME_TAG:-1.16.1}"
export LIBRIME_QJS_TAG LIBRIME_TAG

resolve_version() {
  if [[ -n "${VERSION:-}" ]]; then
    echo "${VERSION#v}"
    return
  fi
  if [[ -n "${GITHUB_REF_NAME:-}" && "${GITHUB_REF_NAME}" == v* ]]; then
    echo "${GITHUB_REF_NAME#v}"
    return
  fi
  if git -C "$PACKAGE_ROOT" describe --tags --exact-match 2>/dev/null | grep -q '^v'; then
    git -C "$PACKAGE_ROOT" describe --tags --exact-match | sed 's/^v//'
    return
  fi
  local schema_ver
  schema_ver="$(
    python3 - "$PACKAGE_ROOT/rime/gujarati.schema.yaml" <<'PY'
import re, sys
text = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"(?m)^\s*version:\s*['\"]?([0-9]+(?:\.[0-9]+)*)", text)
print(m.group(1) if m else "0.0.0")
PY
  )"
  echo "${schema_ver:-0.0.0}-dev"
}

patch_onnx_paths() {
  local schema="$1"
  local socket="$2"
  local helper="$3"
  # portable in-place edit
  if command -v python3 >/dev/null 2>&1; then
    python3 - "$schema" "$socket" "$helper" <<'PY'
import sys
path, sock, helper = sys.argv[1], sys.argv[2], sys.argv[3]
text = open(path, encoding="utf-8").read()
import re
text = re.sub(r'(?m)^(\s*onnx_socket:\s*).*$', r'\1"' + sock + '"', text)
text = re.sub(r'(?m)^(\s*onnx_helper:\s*).*$', r'\1"' + helper + '"', text)
open(path, "w", encoding="utf-8").write(text)
PY
  else
    sed -i.bak \
      -e "s|^[[:space:]]*onnx_socket:.*|  onnx_socket: \"${socket}\"|" \
      -e "s|^[[:space:]]*onnx_helper:.*|  onnx_helper: \"${helper}\"|" \
      "$schema"
    rm -f "${schema}.bak"
  fi
}

require_file() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "ERROR: missing required file: $f" >&2
    exit 1
  fi
}
