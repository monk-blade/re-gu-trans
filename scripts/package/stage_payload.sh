#!/usr/bin/env bash
# Stage shared Rime payload for OS packages (qjs-only; no table dicts).
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
require_file "$RIME_SRC/js/gu_lexicon_blob.json"
require_file "$RIME_SRC/js/lm/unigram.tsv"
require_file "$RIME_SRC/js/lm/stems.json"
require_file "$RIME_SRC/js/lm/attested.json"

# Compact trie text assets (regenerable)
if [[ ! -f "$RIME_SRC/js/lexicon.trie.txt" ]]; then
  python3 "$PACKAGE_ROOT/scripts/build_qjs_tries.py" || true
fi

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/rime/js/lm"

cp -f "$RIME_SRC/gujarati.schema.yaml" "$OUT_DIR/rime/"
# Plugins + assets live once under js/ (qjs resolves @name from userDataDir + js/)
cp -f "$RIME_SRC/js/gujarati_translator.js" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/commit_on_punct_processor.js" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/gu_lexicon_blob.json" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/js/lm/unigram.tsv" "$OUT_DIR/rime/js/lm/"
cp -f "$RIME_SRC/js/lm/stems.json" "$OUT_DIR/rime/js/lm/"
cp -f "$RIME_SRC/js/lm/attested.json" "$OUT_DIR/rime/js/lm/"
cp -f "$RIME_SRC/js/emoji_keywords.json" "$OUT_DIR/rime/js/" 2>/dev/null || true
# Optional ranking policy / tries (P1+)
cp -f "$RIME_SRC/js/ranking_policy.json" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/lexicon.trie.txt" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/prefix.trie.txt" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/native_lm.tsv" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/storage.js" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/ranking.js" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/phonetic.js" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/js/learning.js" "$OUT_DIR/rime/js/" 2>/dev/null || true
cp -f "$RIME_SRC/gujarati.custom.yaml.sample" "$OUT_DIR/rime/" 2>/dev/null || true

# Snippet only — installers merge via deployer / safe patch helpers (never raw append)
cat > "$OUT_DIR/rime/default.custom.yaml.snippet" <<'EOF'
# re-gu-trans: enable Gujarati schema (merge under patch.schema_list)
# Prefer: rime_deployer --add-schema gujarati
  - schema: gujarati
EOF

cat > "$OUT_DIR/VERSION" <<EOF
$VERSION
EOF

cat > "$OUT_DIR/MANIFEST.txt" <<EOF
re-gu-trans payload
version=$VERSION
os=$OS
librime_qjs_tag=$LIBRIME_QJS_TAG
librime_tag=$LIBRIME_TAG
runtime=qjs-only
EOF

echo "Staged payload → $OUT_DIR (version=$VERSION os=$OS)"
find "$OUT_DIR" -type f | sed "s|^$OUT_DIR/||" | sort
