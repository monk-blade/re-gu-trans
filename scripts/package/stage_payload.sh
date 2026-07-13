#!/usr/bin/env bash
# Stage shared Rime payload for OS packages.
#
# Usage:
#   ./scripts/package/stage_payload.sh [OUT_DIR] [OS]
# OS: macos | windows | linux | generic (default: generic)
#
# Env:
#   VERSION          package version (default: from tag / schema)
#   ONNX_SOCKET      override onnx_socket in schema
#   ONNX_HELPER      override onnx_helper in schema

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
require_file "$RIME_SRC/gujarati.dict.yaml"
require_file "$RIME_SRC/gujarati_translator.js"
require_file "$RIME_SRC/commit_on_punct_processor.js"
require_file "$RIME_SRC/gu_lexicon_blob.json"
require_file "$RIME_SRC/js/lm/unigram.tsv"
require_file "$RIME_SRC/js/lm/stems.json"
require_file "$RIME_SRC/js/lm/attested.json"

rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR/rime/js/lm"

cp -f "$RIME_SRC/gujarati.schema.yaml" "$OUT_DIR/rime/"
cp -f "$RIME_SRC/gujarati.dict.yaml" "$OUT_DIR/rime/"
cp -f "$RIME_SRC/gujarati_apple.dict.yaml" "$OUT_DIR/rime/" 2>/dev/null || true

cp -f "$RIME_SRC/gujarati_translator.js" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/commit_on_punct_processor.js" "$OUT_DIR/rime/js/"
cp -f "$RIME_SRC/gu_lexicon_blob.json" "$OUT_DIR/rime/js/"
# Also at rime root for sync_rime compatibility
cp -f "$RIME_SRC/gujarati_translator.js" "$OUT_DIR/rime/"
cp -f "$RIME_SRC/commit_on_punct_processor.js" "$OUT_DIR/rime/"
cp -f "$RIME_SRC/gu_lexicon_blob.json" "$OUT_DIR/rime/"

cp -f "$RIME_SRC/js/lm/unigram.tsv" "$OUT_DIR/rime/js/lm/"
cp -f "$RIME_SRC/js/lm/stems.json" "$OUT_DIR/rime/js/lm/"
cp -f "$RIME_SRC/js/lm/attested.json" "$OUT_DIR/rime/js/lm/"
cp -f "$RIME_SRC/js/emoji_keywords.json" "$OUT_DIR/rime/js/" 2>/dev/null || true

# Default onnx paths per OS (packages do not ship the ranker; paths are harmless)
case "$OS" in
  macos)
    SOCK="${ONNX_SOCKET:-~/Library/Rime/run/gu_ranker.sock}"
    HELP="${ONNX_HELPER:-~/Library/Rime/run/gu_ranker_client}"
    ;;
  windows)
    SOCK="${ONNX_SOCKET:-%APPDATA%/Rime/run/gu_ranker.sock}"
    HELP="${ONNX_HELPER:-%APPDATA%/Rime/run/gu_ranker_client.bat}"
    ;;
  linux)
    SOCK="${ONNX_SOCKET:-~/.local/share/fcitx5/rime/run/gu_ranker.sock}"
    HELP="${ONNX_HELPER:-~/.local/share/fcitx5/rime/run/gu_ranker_client}"
    ;;
  *)
    SOCK="${ONNX_SOCKET:-~/Library/Rime/run/gu_ranker.sock}"
    HELP="${ONNX_HELPER:-~/Library/Rime/run/gu_ranker_client}"
    ;;
esac
patch_onnx_paths "$OUT_DIR/rime/gujarati.schema.yaml" "$SOCK" "$HELP"

cat > "$OUT_DIR/rime/default.custom.yaml" <<'EOF'
# re-gu-trans: enable Gujarati schema
# Merge with your existing default.custom.yaml if you already have one.
patch:
  schema_list:
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
EOF

echo "Staged payload → $OUT_DIR (version=$VERSION os=$OS)"
find "$OUT_DIR" -type f | sed "s|^$OUT_DIR/||" | sort
