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

# --- download librime-qjs ---
API="https://api.github.com/repos/HuangJian/librime-qjs/releases/tags/${LIBRIME_QJS_TAG}"
echo "Resolving librime-qjs asset for ${LIBRIME_QJS_TAG} ..."
ASSET_URL="$(
  python3 - <<PY
import json, os, urllib.request
url = "$API"
headers = {"Accept": "application/vnd.github+json", "User-Agent": "re-gu-trans"}
token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
if token:
    headers["Authorization"] = "token " + token
req = urllib.request.Request(url, headers=headers)
data = json.load(urllib.request.urlopen(req))
for a in data.get("assets", []):
    name = a.get("name", "")
    if "macOS-ARM64" in name and name.endswith((".tar.bz2", ".tar.gz", ".tgz")):
        print(a["browser_download_url"])
        break
else:
    raise SystemExit("no macOS-ARM64 asset found")
PY
)"
ARCHIVE="$QJS_CACHE/$(basename "$ASSET_URL")"
if [[ ! -f "$ARCHIVE" ]]; then
  curl -fL -o "$ARCHIVE" "$ASSET_URL"
fi
EXTRACT="$QJS_CACHE/extract"
rm -rf "$EXTRACT"
mkdir -p "$EXTRACT"
tar xjf "$ARCHIVE" -C "$EXTRACT" 2>/dev/null || tar xzf "$ARCHIVE" -C "$EXTRACT"
DYLIB="$(find "$EXTRACT" -name 'librime-qjs.dylib' | head -1)"
require_file "$DYLIB"

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
(
  cd "$ZIP_DIR"
  zip -r "$OUT_DIR/re-gu-trans-${VERSION}-macos-arm64.zip" .
)

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
