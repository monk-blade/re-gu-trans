#!/usr/bin/env bash
# Stage shared Rime payload for OS packages (qjs-only; binary Tries preferred).
#
# Usage:
#   ./scripts/package/stage_payload.sh [OUT_DIR] [OS]
# OS: macos | windows | linux | generic (default: generic)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

OUT_DIR="${1:-$PACKAGE_ROOT/dist/payload}"
OS="${2:-generic}"
VERSION="$(resolve_version)"
export VERSION
export COPYFILE_DISABLE=1

RIME_SRC="$PACKAGE_ROOT/rime"
require_file "$RIME_SRC/gujarati.schema.yaml"
require_file "$RIME_SRC/js/gujarati_translator.js"
require_file "$RIME_SRC/js/commit_on_punct_processor.js"
require_file "$RIME_SRC/js/ranking_policy.json"

# Ensure Tries exist (text always; binary when marisa-trie available)
python3 "$PACKAGE_ROOT/scripts/build_qjs_tries.py" --bin --exceptions || \
  python3 "$PACKAGE_ROOT/scripts/build_qjs_tries.py" --exceptions || true

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/rime/js/lm"

cp -f "$RIME_SRC/gujarati.schema.yaml" "$OUT_DIR/rime/"
cp -f "$RIME_SRC/js/gujarati_translator.js" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/commit_on_punct_processor.js" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/ranking.js" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/phonetic.js" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/storage.js" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/learning.js" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/ranking_policy.json" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/emoji_keywords.json" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/exceptions.json" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/ltr_coefficients.json" "$OUT_DIR/rime/js/" 2>/dev/null || true

# Prefer binary Tries; omit multi-MB JSON/TSV from release when bins present
if [[ -f "$RIME_SRC/js/lexicon.trie.bin" && -f "$RIME_SRC/js/prefix.trie.bin" && -f "$RIME_SRC/js/native_lm.trie.bin" ]]; then
  cp -f "$RIME_SRC/js/lexicon.trie.bin" "$OUT_DIR/rime/js/"
  cp -f "$RIME_SRC/js/prefix.trie.bin" "$OUT_DIR/rime/js/"
  cp -f "$RIME_SRC/js/native_lm.trie.bin" "$OUT_DIR/rime/js/"
  echo "Staged binary Tries (no gu_lexicon_blob.json / LM TSV in payload)"
else
  echo "WARN: binary Tries missing — fall back to JSON/LM assets" >&2
  require_file "$RIME_SRC/js/gu_lexicon_blob.json"
  require_file "$RIME_SRC/js/lm/unigram.tsv"
  cp -f "$RIME_SRC/js/gu_lexicon_blob.json" "$OUT_DIR/rime/js/"
  cp -f "$RIME_SRC/js/lm/unigram.tsv" "$OUT_DIR/rime/js/lm/"
  cp -f "$RIME_SRC/js/lm/stems.json" "$OUT_DIR/rime/js/lm/"
  cp -f "$RIME_SRC/js/lm/attested.json" "$OUT_DIR/rime/js/lm/"
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

# SHA-256 manifest for release provenance
{
  echo "re-gu-trans payload"
  echo "version=$VERSION"
  echo "os=$OS"
  echo "librime_qjs_tag=$LIBRIME_QJS_TAG"
  echo "librime_tag=$LIBRIME_TAG"
  echo "runtime=qjs-only"
  echo "writeFileAtomic=patched-overlay"
  echo "--- sha256 ---"
  (cd "$OUT_DIR" && find . -type f | sort | while read -r f; do
    shasum -a 256 "$f" | awk '{print $1"  "$2}'
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
