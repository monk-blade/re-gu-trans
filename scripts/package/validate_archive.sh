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
  *.deb)
    if command -v dpkg-deb >/dev/null 2>&1; then
      dpkg-deb -x "$ARCHIVE" "$TMP"
    else
      command -v ar >/dev/null 2>&1 || { echo "FAIL: ar is required to inspect .deb on this host" >&2; exit 1; }
      DEB_TMP="$TMP/deb-ar"
      mkdir -p "$DEB_TMP"
      (cd "$DEB_TMP" && ar x "$ARCHIVE")
      test -f "$DEB_TMP/data.tar.gz" || {
        echo "FAIL: unsupported .deb data archive without dpkg-deb" >&2
        exit 1
      }
      tar -xzf "$DEB_TMP/data.tar.gz" -C "$TMP"
    fi
    ;;
  *.rpm)
    command -v rpm2cpio >/dev/null
    CPIO_LOG="$TMP/cpio.stderr"
    set +e
    rpm2cpio "$ARCHIVE" | (
      cd "$TMP" && cpio --no-absolute-filenames -idm --quiet 2>"$CPIO_LOG"
    )
    CPIO_STATUS=$?
    set -e
    if [[ "$CPIO_STATUS" -ne 0 ]]; then
      if [[ "$CPIO_STATUS" -eq 1 ]] &&
        grep -q 'Removing leading.*from member names' "$CPIO_LOG" &&
        ! grep -qv 'Removing leading.*from member names' "$CPIO_LOG"; then
        echo "RPM extraction normalized absolute member names"
      else
        cat "$CPIO_LOG" >&2
        exit "$CPIO_STATUS"
      fi
    fi
    rm -f "$CPIO_LOG"
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
