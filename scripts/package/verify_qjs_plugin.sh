#!/usr/bin/env bash
# Static release gate for the patched QJS runtime surface. Real calls are tested by the Rime harness.
set -euo pipefail
PLUGIN="${1:?plugin dylib/so/dll}"
test -f "$PLUGIN" || { echo "FAIL: missing plugin $PLUGIN" >&2; exit 1; }

if command -v strings >/dev/null 2>&1; then
  TEXT="$(strings "$PLUGIN")"
else
  TEXT="$(LC_ALL=C grep -a -o -E 'writeFileAtomic|getCandidateAt|commitNotifier|prefixSearch|loadBinaryFile' "$PLUGIN" || true)"
fi

for symbol in writeFileAtomic getCandidateAt commitNotifier prefixSearch loadBinaryFile; do
  if ! grep -q "$symbol" <<<"$TEXT"; then
    echo "FAIL: $PLUGIN lacks required QJS capability marker $symbol" >&2
    exit 1
  fi
done

echo "VERIFY_QJS_PLUGIN_OK plugin=$PLUGIN"
