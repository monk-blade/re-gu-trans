#!/usr/bin/env bash
# Stage Linux package tree and build .deb + .rpm via nfpm.
#
# Prerequisites (CI):
#   - librime-qjs.so already built (or build here)
#   - nfpm installed
#
# Usage:
#   ./scripts/package/linux/build_packages.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common.sh
source "$SCRIPT_DIR/../common.sh"

VERSION="$(resolve_version)"
export VERSION
DIST="$PACKAGE_ROOT/dist"
STAGE="$DIST/linux-root"
PAYLOAD="$DIST/payload-linux"
PLUGIN_SO="${PLUGIN_SO:-$DIST/plugins/librime-qjs.so}"
OUT_DIR="$DIST/packages"
NFPM_CONFIG="$PACKAGE_ROOT/packaging/nfpm.yaml"

mkdir -p "$OUT_DIR" "$DIST/plugins"

if [[ ! -f "$PLUGIN_SO" ]]; then
  echo "Building librime-qjs.so ..."
  "$SCRIPT_DIR/build_librime_qjs.sh"
fi
require_file "$PLUGIN_SO"

"$SCRIPT_DIR/../stage_payload.sh" "$PAYLOAD" linux

rm -rf "$STAGE"
mkdir -p \
  "$STAGE/usr/lib/rime-plugins" \
  "$STAGE/usr/lib/x86_64-linux-gnu/rime-plugins" \
  "$STAGE/usr/share/rime-data/js/lm" \
  "$STAGE/usr/share/re-gu-trans/snippets" \
  "$STAGE/usr/bin"

# Plugin (both common search paths)
cp -f "$PLUGIN_SO" "$STAGE/usr/lib/rime-plugins/librime-qjs.so"
cp -f "$PLUGIN_SO" "$STAGE/usr/lib/x86_64-linux-gnu/rime-plugins/librime-qjs.so"

# Shared Rime data (schemas + JS loadable via sharedDataDir) — qjs-only
cp -f "$PAYLOAD/rime/gujarati.schema.yaml" "$STAGE/usr/share/rime-data/"
cp -f "$PAYLOAD/rime/js/"*.js "$STAGE/usr/share/rime-data/js/"
cp -f "$PAYLOAD/rime/js/gu_lexicon_blob.json" "$STAGE/usr/share/rime-data/js/"
cp -f "$PAYLOAD/rime/js/lm/"* "$STAGE/usr/share/rime-data/js/lm/"
cp -f "$PAYLOAD/rime/js/ranking_policy.json" "$STAGE/usr/share/rime-data/js/" 2>/dev/null || true

# Vendor copy + enable helper
cp -a "$PAYLOAD/rime" "$STAGE/usr/share/re-gu-trans/"
cp -f "$PAYLOAD/rime/default.custom.yaml.snippet" "$STAGE/usr/share/re-gu-trans/snippets/" 2>/dev/null || true
cp -f "$PACKAGE_ROOT/packaging/linux/re-gu-trans-enable" "$STAGE/usr/bin/"
chmod 755 "$STAGE/usr/bin/re-gu-trans-enable"

# Generate nfpm config with version substituted
TMP_NFPM="$(mktemp)"
sed "s/__VERSION__/${VERSION}/g" "$NFPM_CONFIG" > "$TMP_NFPM"

if ! command -v nfpm >/dev/null 2>&1; then
  echo "Installing nfpm..."
  curl -sL "https://github.com/goreleaser/nfpm/releases/download/v2.41.3/nfpm_2.41.3_Linux_x86_64.tar.gz" \
    | tar xz -C /tmp nfpm
  export PATH="/tmp:$PATH"
fi

(
  cd "$PACKAGE_ROOT"
  nfpm package --config "$TMP_NFPM" --packager deb --target "$OUT_DIR/"
  nfpm package --config "$TMP_NFPM" --packager rpm --target "$OUT_DIR/"
)
rm -f "$TMP_NFPM"

echo "Linux packages:"
ls -la "$OUT_DIR"/*.{deb,rpm} 2>/dev/null || ls -la "$OUT_DIR"
