#!/usr/bin/env bash
# Assert staged or packaged payload meets binary-only release contract.
# Usage: ./scripts/package/validate_payload.sh PAYLOAD_DIR
set -euo pipefail
PAYLOAD="${1:?payload dir}"
JS="$PAYLOAD/rime/js"
if [[ ! -d "$JS" ]]; then
  # flat zip layouts use payload/rime/js or just rime/js
  if [[ -d "$PAYLOAD/js" ]]; then
    JS="$PAYLOAD/js"
  elif [[ -d "$PAYLOAD/payload/rime/js" ]]; then
    JS="$PAYLOAD/payload/rime/js"
  else
    echo "FAIL: cannot find rime/js under $PAYLOAD" >&2
    exit 1
  fi
fi

for bin in lexicon.trie.bin prefix.trie.bin native_lm.trie.bin; do
  test -f "$JS/$bin" || { echo "FAIL: missing $JS/$bin" >&2; exit 1; }
done
! test -f "$JS/gu_lexicon_blob.json" || { echo "FAIL: blob present in $JS" >&2; exit 1; }
! test -f "$JS/lm/unigram.tsv" || { echo "FAIL: unigram present in $JS" >&2; exit 1; }
test -f "$JS/gujarati_translator.js" || { echo "FAIL: missing translator" >&2; exit 1; }
test -f "$JS/ranking_policy.json" || { echo "FAIL: missing ranking_policy" >&2; exit 1; }
test -f "$JS/native_lm_meta.json" || { echo "FAIL: missing native LM metadata" >&2; exit 1; }

python3 - "$JS/native_lm_meta.json" <<'PY'
import json
import sys
meta = json.load(open(sys.argv[1], encoding="utf-8"))
assert meta.get("version") == 1
assert meta.get("payload_format") == "unigram\\tstem\\tattested"
assert int(meta.get("max_unigram") or 0) > 0
assert int(meta.get("attested_floor") or 0) >= 0
PY

TOTAL=0
while IFS= read -r -d '' f; do
  size=$(wc -c <"$f")
  TOTAL=$((TOTAL + size))
done < <(find "$PAYLOAD" -type f -print0 2>/dev/null || true)
MAX=$((70 * 1024 * 1024))
if [[ "$TOTAL" -gt "$MAX" ]]; then
  echo "FAIL: payload $TOTAL bytes > 70MB" >&2
  exit 1
fi
echo "VALIDATE_PAYLOAD_OK js=$JS bytes=$TOTAL"
