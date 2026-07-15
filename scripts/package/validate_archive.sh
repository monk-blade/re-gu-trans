#!/usr/bin/env bash
# Validate an extracted release archive, including the patched runtime plugin.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ARCHIVE_INPUT="${1:?package archive}"
ARCHIVE="$(cd "$(dirname "$ARCHIVE_INPUT")" && pwd)/$(basename "$ARCHIVE_INPUT")"
TMP="${TMPDIR:-/tmp}/re-gu-trans-archive-$$"
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT

case "$ARCHIVE" in
  *.zip) unzip -q "$ARCHIVE" -d "$TMP" ;;
  *.deb) dpkg-deb -x "$ARCHIVE" "$TMP" ;;
  *.rpm)
    command -v rpm2cpio >/dev/null
    (cd "$TMP" && rpm2cpio "$ARCHIVE" | cpio -idm --quiet)
    ;;
  *.pkg)
    command -v pkgutil >/dev/null
    pkgutil --expand-full "$ARCHIVE" "$TMP/pkg"
    ;;
  *) echo "FAIL: unsupported package $ARCHIVE" >&2; exit 2 ;;
esac

PAYLOAD=""
while IFS= read -r candidate; do
  PAYLOAD="$(dirname "$(dirname "$(dirname "$candidate")")")"
  break
done < <(find "$TMP" -type f -path '*/rime/js/native_lm_meta.json' | head -1)
test -n "$PAYLOAD" || { echo "FAIL: no packaged rime/js payload in $ARCHIVE" >&2; exit 1; }
"$ROOT/scripts/package/validate_payload.sh" "$PAYLOAD"

PLUGIN="$(find "$TMP" -type f \( -name 'librime-qjs.so' -o -name 'librime-qjs.dylib' -o -name 'rime.dll' \) | head -1 || true)"
test -n "$PLUGIN" || { echo "FAIL: runtime plugin absent from $ARCHIVE" >&2; exit 1; }
"$ROOT/scripts/package/verify_qjs_plugin.sh" "$PLUGIN"
if [[ -n "${EXPECTED_PLUGIN_SHA256:-}" ]]; then
  if command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_PLUGIN_SHA256="$(sha256sum "$PLUGIN" | awk '{print $1}')"
  else
    ACTUAL_PLUGIN_SHA256="$(shasum -a 256 "$PLUGIN" | awk '{print $1}')"
  fi
  test "$ACTUAL_PLUGIN_SHA256" = "$EXPECTED_PLUGIN_SHA256" || {
    echo "FAIL: packaged plugin hash differs from tested plugin" >&2
    exit 1
  }
fi
echo "VALIDATE_ARCHIVE_OK archive=$ARCHIVE plugin=$PLUGIN"
