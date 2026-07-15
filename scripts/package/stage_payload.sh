#!/usr/bin/env bash
# Stage shared Rime payload for OS packages (qjs-only; binary Tries required for release).
#
# Usage:
#   ./scripts/package/stage_payload.sh [OUT_DIR] [OS]
# OS: macos | windows | linux | generic (default: generic)
#
# Env:
#   REQUIRE_BINARY_TRIES=1  (default) — fail if bins missing; never stage blob/LM
#   ALLOW_TEXT_FALLBACK=1             — local/dev only: allow JSON+TSV fallback

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

OUT_DIR="${1:-$PACKAGE_ROOT/dist/payload}"
OS="${2:-generic}"
VERSION="$(resolve_version)"
export VERSION
export COPYFILE_DISABLE=1

REQUIRE_BINARY_TRIES="${REQUIRE_BINARY_TRIES:-1}"
ALLOW_TEXT_FALLBACK="${ALLOW_TEXT_FALLBACK:-0}"
if [[ "$ALLOW_TEXT_FALLBACK" == "1" ]]; then
  REQUIRE_BINARY_TRIES=0
fi

RIME_SRC="$PACKAGE_ROOT/rime"
require_file "$RIME_SRC/gujarati.schema.yaml"
require_file "$RIME_SRC/js/gujarati_translator.js"
require_file "$RIME_SRC/js/commit_on_punct_processor.js"
require_file "$RIME_SRC/js/ranking_policy.json"
require_file "$RIME_SRC/js/native_lm_meta.json"

echo "== build Tries (REQUIRE_BINARY_TRIES=$REQUIRE_BINARY_TRIES ALLOW_TEXT_FALLBACK=$ALLOW_TEXT_FALLBACK) =="
if [[ "$REQUIRE_BINARY_TRIES" == "1" ]]; then
  python3 "$PACKAGE_ROOT/scripts/build_qjs_tries.py" --bin --exceptions
else
  python3 "$PACKAGE_ROOT/scripts/build_qjs_tries.py" --bin --exceptions || \
    python3 "$PACKAGE_ROOT/scripts/build_qjs_tries.py" --exceptions
fi

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/rime/js"

cp -f "$RIME_SRC/gujarati.schema.yaml" "$OUT_DIR/rime/"
# Generic copy of production JS modules + small JSON (no exclusive fallback names)
cp -f "$RIME_SRC/js/"*.js "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/ranking_policy.json" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/native_lm_meta.json" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/emoji_keywords.json" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/exceptions.json" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/ltr_coefficients.json" "$OUT_DIR/rime/js/" 2>/dev/null || true

HAS_BINS=0
if [[ -f "$RIME_SRC/js/lexicon.trie.bin" && -f "$RIME_SRC/js/prefix.trie.bin" && -f "$RIME_SRC/js/native_lm.trie.bin" ]]; then
  HAS_BINS=1
fi

if [[ "$HAS_BINS" -eq 1 ]]; then
  cp -f "$RIME_SRC/js/lexicon.trie.bin" "$OUT_DIR/rime/js/"
  cp -f "$RIME_SRC/js/prefix.trie.bin" "$OUT_DIR/rime/js/"
  cp -f "$RIME_SRC/js/native_lm.trie.bin" "$OUT_DIR/rime/js/"
  echo "Staged binary Tries (no gu_lexicon_blob.json / LM TSV in payload)"
elif [[ "$REQUIRE_BINARY_TRIES" == "1" ]]; then
  echo "FAIL: binary Tries required but missing under rime/js/*.trie.bin" >&2
  echo "Install marisa-trie and run: python3 scripts/build_qjs_tries.py --bin --exceptions" >&2
  exit 1
else
  echo "WARN: binary Tries missing — ALLOW_TEXT_FALLBACK staging JSON/LM" >&2
  mkdir -p "$OUT_DIR/rime/js/lm"
  require_file "$RIME_SRC/js/gu_lexicon_blob.json"
  require_file "$RIME_SRC/js/lm/unigram.tsv"
  cp -f "$RIME_SRC/js/gu_lexicon_blob.json" "$OUT_DIR/rime/js/"
  cp -f "$RIME_SRC/js/lm/unigram.tsv" "$OUT_DIR/rime/js/lm/"
  cp -f "$RIME_SRC/js/lm/stems.json" "$OUT_DIR/rime/js/lm/"
  cp -f "$RIME_SRC/js/lm/attested.json" "$OUT_DIR/rime/js/lm/"
fi

# Release contract: never ship large build inputs when bins are staged
if [[ "$HAS_BINS" -eq 1 ]]; then
  ! test -f "$OUT_DIR/rime/js/gu_lexicon_blob.json" || {
    echo "FAIL: blob must not be in binary payload" >&2
    exit 1
  }
  ! test -f "$OUT_DIR/rime/js/lm/unigram.tsv" || {
    echo "FAIL: unigram.tsv must not be in binary payload" >&2
    exit 1
  }
fi

cp -f "$RIME_SRC/gujarati.custom.yaml.sample" "$OUT_DIR/rime/" 2>/dev/null || true

cat > "$OUT_DIR/rime/default.custom.yaml.snippet" <<'EOF'
# re-gu-trans: enable Gujarati schema (merge under patch.schema_list)
# Prefer: rime_deployer --add-schema gujarati
  - schema: gujarati
EOF

cat > "$OUT_DIR/VERSION" <<EOF
$VERSION
EOF

{
  echo "re-gu-trans payload"
  echo "version=$VERSION"
  echo "os=$OS"
  echo "librime_qjs_tag=$LIBRIME_QJS_TAG"
  echo "librime_tag=$LIBRIME_TAG"
  echo "runtime=qjs-only"
  echo "binary_tries=$HAS_BINS"
  echo "writeFileAtomic=patched-overlay"
  echo "--- sha256 ---"
  (cd "$OUT_DIR" && find . -type f | sort | while read -r f; do
    sha256_file "$f" | awk '{print $1"  "$2}'
  done)
} > "$OUT_DIR/MANIFEST.txt"

echo "Staged payload → $OUT_DIR (version=$VERSION os=$OS)"
find "$OUT_DIR" -type f | sed "s|^$OUT_DIR/||" | sort

TOTAL=0
while IFS= read -r -d '' f; do
  if size=$(wc -c <"$f" 2>/dev/null); then
    TOTAL=$((TOTAL + size))
  fi
done < <(find "$OUT_DIR" -type f -print0 2>/dev/null)

echo "payload_bytes=$TOTAL"
MAX=$((70 * 1024 * 1024))
if [[ "$TOTAL" -gt "$MAX" ]]; then
  echo "FAIL: payload exceeds 70MB ($TOTAL > $MAX)" >&2
  exit 1
fi
