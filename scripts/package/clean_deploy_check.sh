#!/usr/bin/env bash
# Validate staged payload installs into an empty Rime user dir (never ~/Library/Rime).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

STAGE="${TMPDIR:-/tmp}/re-gu-trans-clean-deploy-$$"
RIME_USER="${STAGE}/rime-user"
PAYLOAD="${STAGE}/payload"
mkdir -p "$STAGE"

cleanup() { rm -rf "$STAGE"; }
trap cleanup EXIT

echo "== stage_payload =="
./scripts/package/stage_payload.sh "$PAYLOAD" generic

echo "== install into empty user dir =="
export RIME_USER_DIR="$RIME_USER"
mkdir -p "$RIME_USER/js"

cp -f "$PAYLOAD/rime/gujarati.schema.yaml" "$RIME_USER/"
cp -f "$PAYLOAD/rime/js/"*.js "$RIME_USER/js/"
cp -f "$PAYLOAD/rime/js/"*.json "$RIME_USER/js/" 2>/dev/null || true
cp -f "$PAYLOAD/rime/js/"*.bin "$RIME_USER/js/" 2>/dev/null || true
if [[ -d "$PAYLOAD/rime/js/lm" ]]; then
  mkdir -p "$RIME_USER/js/lm"
  cp -f "$PAYLOAD/rime/js/lm/"* "$RIME_USER/js/lm/" 2>/dev/null || true
fi
# qjs resolves @plugin from user-dir root
cp -f "$PAYLOAD/rime/js/gujarati_translator.js" "$RIME_USER/"
cp -f "$PAYLOAD/rime/js/commit_on_punct_processor.js" "$RIME_USER/"
if [[ -f "$PAYLOAD/rime/default.custom.yaml.snippet" ]]; then
  cat > "$RIME_USER/default.custom.yaml" <<'EOF'
patch:
  schema_list:
    - schema: gujarati
EOF
fi

echo "== assert required files =="
for f in \
  gujarati.schema.yaml \
  gujarati_translator.js \
  commit_on_punct_processor.js \
  js/ranking_policy.json \
  js/ranking.js \
  js/storage.js
do
  test -f "$RIME_USER/$f" || { echo "MISSING $f"; exit 1; }
done

if [[ -f "$RIME_USER/js/lexicon.trie.bin" ]]; then
  echo "OK binary lexicon trie present"
else
  test -f "$RIME_USER/js/gu_lexicon_blob.json" || { echo "MISSING lexicon blob and trie.bin"; exit 1; }
  test -f "$RIME_USER/js/lm/unigram.tsv" || { echo "MISSING unigram"; exit 1; }
fi

echo "== forbid broken / table-dict runtime deps =="
! test -f "$PAYLOAD/rime/gujarati_apple.dict.yaml" || { echo "FAIL: apple dict still packaged"; exit 1; }
! test -f "$PAYLOAD/rime/gujarati_extra.dict.yaml" || { echo "FAIL: gujarati_extra packaged"; exit 1; }
! test -f "$PAYLOAD/rime/gujarati_learned.dict.yaml" || { echo "FAIL: gujarati_learned packaged"; exit 1; }

if grep -R "gujarati_extra\|gujarati_learned" "$PAYLOAD/rime" --include='*.yaml' 2>/dev/null | grep -v '^[^:]*:#'; then
  echo "FAIL: payload still references gujarati_extra/learned"
  exit 1
fi

if grep -E '^\s*dictionary:\s*gujarati' "$PAYLOAD/rime/gujarati.schema.yaml"; then
  echo "FAIL: schema still declares table dictionary: gujarati"
  exit 1
fi

ROOT_JS_DUP=0
test -f "$PAYLOAD/rime/gujarati_translator.js" && ROOT_JS_DUP=1 || true
if [[ "$ROOT_JS_DUP" -eq 1 ]]; then
  echo "FAIL: payload has root duplicate translator (must be js/ only)"
  exit 1
fi

# CI sets REQUIRE_RIME_DEPLOYER=1 — missing/failing deployer is a hard fail.
REQUIRE_RIME_DEPLOYER="${REQUIRE_RIME_DEPLOYER:-0}"
if command -v rime_deployer >/dev/null 2>&1; then
  echo "== rime_deployer =="
  if ! rime_deployer --build "$RIME_USER"; then
    if [[ "$REQUIRE_RIME_DEPLOYER" == "1" ]]; then
      echo "FAIL: rime_deployer --build failed"
      exit 1
    fi
    echo "WARN: rime_deployer --build failed (may need shared data); schema files still OK"
  fi
else
  if [[ "$REQUIRE_RIME_DEPLOYER" == "1" ]]; then
    echo "FAIL: rime_deployer not installed (REQUIRED)"
    exit 1
  fi
  echo "NOTE: rime_deployer not installed; file-level clean-deploy checks passed"
fi

echo "CLEAN_DEPLOY_OK user=$RIME_USER"
