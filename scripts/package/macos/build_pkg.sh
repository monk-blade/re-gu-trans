#!/usr/bin/env bash
# Build macOS .pkg and .zip for re-gu-trans (Apple Silicon / ARM64).
#
# Downloads librime-qjs macOS-ARM64 from HuangJian releases.
# Requires: macOS host with pkgbuild/productbuild (CI: macos-14).
#
# Important: do NOT stage files under Squirrel.app in the pkg root — pkgbuild
# would treat it as a bundle replace. Plugin is copied into Squirrel in postinstall.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../common.sh
source "$SCRIPT_DIR/../common.sh"

VERSION="$(resolve_version)"
export VERSION
DIST="$PACKAGE_ROOT/dist"
PAYLOAD="$DIST/payload-macos"
PKG_ROOT="$DIST/macos-pkgroot"
SCRIPTS_DIR="$DIST/macos-scripts"
OUT_DIR="$DIST/packages"
QJS_CACHE="$DIST/qjs-macos"
IDENTIFIER="com.re-gu-trans.pkg"

mkdir -p "$OUT_DIR" "$QJS_CACHE"
# Avoid AppleDouble ._* files in packages
export COPYFILE_DISABLE=1

"$SCRIPT_DIR/../stage_payload.sh" "$PAYLOAD" macos

# Prefer patched plugin built from source + overlay (required for learning).
DYLIB="${OUT_DYLIB:-$DIST/plugins/librime-qjs.dylib}"
REQUIRE_PATCHED_QJS="${REQUIRE_PATCHED_QJS:-1}"
if [[ ! -f "$DYLIB" ]]; then
  if [[ "$REQUIRE_PATCHED_QJS" == "1" ]]; then
    echo "Building patched librime-qjs.dylib from source..."
    chmod +x "$SCRIPT_DIR/build_librime_qjs.sh"
    "$SCRIPT_DIR/build_librime_qjs.sh"
  else
    ASSET_URL="$(resolve_qjs_asset_url macos-arm64)"
    echo "WARN: downloading unpatched librime-qjs: $ASSET_URL" >&2
    ARCHIVE="$QJS_CACHE/$(basename "$ASSET_URL")"
    download_file "$ASSET_URL" "$ARCHIVE"
    EXTRACT="$QJS_CACHE/extract"
    rm -rf "$EXTRACT"
    mkdir -p "$EXTRACT"
    tar xjf "$ARCHIVE" -C "$EXTRACT" 2>/dev/null || tar xzf "$ARCHIVE" -C "$EXTRACT"
    DYLIB="$(find "$EXTRACT" -name 'librime-qjs.dylib' | head -1)"
  fi
fi
require_file "$DYLIB"
"$PACKAGE_ROOT/scripts/package/verify_qjs_plugin.sh" "$DYLIB"

# --- zip (script install) ---
ZIP_DIR="$DIST/macos-zip"
rm -rf "$ZIP_DIR"
mkdir -p "$ZIP_DIR/payload" "$ZIP_DIR/plugin"
cp -a "$PAYLOAD/." "$ZIP_DIR/payload/"
cp -f "$DYLIB" "$ZIP_DIR/plugin/librime-qjs.dylib"
cp -f "$SCRIPT_DIR/install.sh" "$ZIP_DIR/install.sh"
chmod +x "$ZIP_DIR/install.sh"
cat > "$ZIP_DIR/README.txt" <<EOF
re-gu-trans ${VERSION} (macOS arm64)
1. Install Squirrel: https://github.com/rime/squirrel/releases
2. Run: sudo ./install.sh
3. System Settings → Keyboard → Input Sources → Squirrel → Gujarati
Requires Apple Silicon. Intel Macs: build librime-qjs yourself (no official Intel release).
Pinned librime-qjs: ${LIBRIME_QJS_TAG}
EOF
zip_dir_contents "$ZIP_DIR" "$OUT_DIR/re-gu-trans-${VERSION}-macos-arm64.zip"

# --- pkg (files only under /usr/local/share/re-gu-trans) ---
rm -rf "$PKG_ROOT" "$SCRIPTS_DIR"
mkdir -p \
  "$PKG_ROOT/usr/local/share/re-gu-trans/plugin" \
  "$SCRIPTS_DIR"

cp -a "$PAYLOAD/rime" "$PKG_ROOT/usr/local/share/re-gu-trans/"
cp -f "$PAYLOAD/VERSION" "$PKG_ROOT/usr/local/share/re-gu-trans/"
cp -f "$DYLIB" "$PKG_ROOT/usr/local/share/re-gu-trans/plugin/librime-qjs.dylib"

cp -f "$SCRIPT_DIR/postinstall" "$SCRIPTS_DIR/postinstall"
chmod 755 "$SCRIPTS_DIR/postinstall"

PKG_TMP="$OUT_DIR/re-gu-trans-${VERSION}-macos-arm64-component.pkg"
PKG_OUT="$OUT_DIR/re-gu-trans-${VERSION}-macos-arm64.pkg"

# --analyze can create a component plist; flat /usr/local tree needs no bundles
pkgbuild \
  --root "$PKG_ROOT" \
  --scripts "$SCRIPTS_DIR" \
  --identifier "$IDENTIFIER" \
  --version "$VERSION" \
  --install-location "/" \
  --ownership recommended \
  "$PKG_TMP"

productbuild --package "$PKG_TMP" "$PKG_OUT"
rm -f "$PKG_TMP"

codesign --force --sign - "$PKG_OUT" 2>/dev/null || true

echo "macOS packages:"
ls -la "$OUT_DIR"/re-gu-trans-"${VERSION}"-macos-arm64.*
"$SCRIPT_DIR/../validate_archive.sh" "$OUT_DIR/re-gu-trans-${VERSION}-macos-arm64.zip"
"$SCRIPT_DIR/../validate_archive.sh" "$PKG_OUT"
