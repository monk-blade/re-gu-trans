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

# MODEL_ARCH selects which neural backend this build bundles: "indicxlit"
# (default, higher accuracy, ~20ms/query) or "ctc" (gu-transformer-ctc-v3,
# lower accuracy, ~2ms/query). The native plugin auto-detects either
# architecture's files at load time, so the same librime-qjs.so and plugin
# binary work for both; only the packaged model files and package identity
# differ. The two are named distinctly and marked conflicting since they
# install to the same paths and are meant to be alternatives, not co-installed.
MODEL_ARCH="${MODEL_ARCH:-indicxlit}"
case "$MODEL_ARCH" in
  indicxlit)
    PKG_NAME="${PKG_NAME:-re-gu-trans-xlit}"
    MODEL_SOURCE_DEFAULT="$PACKAGE_ROOT/models/artifacts/gu-indicxlit-v1"
    MODEL_PACK_DEFAULT="$DIST/gujarati-model-pack-linux-xlit"
    CONFLICT_PKG="re-gu-trans-ctc"
    PLUGIN_SOURCE_DEFAULT="$PACKAGE_ROOT/native/gujarati-model-plugin"
    PKG_DESC="Gujarati roman-to-script transliteration for Rime (lexicon + QuickJS), with the IndicXlit neural model (higher accuracy, ~20ms/query), fcitx5, and the Ori theme + Noto Serif Gujarati candidate font all installed as part of this package. On a system with a desktop session, installing this package enables Gujarati typing directly; otherwise run re-gu-trans-enable once as your user. Conflicts with re-gu-trans-ctc (same schema, faster/lower-accuracy CTC model) -- install one or the other."
    ;;
  ctc)
    PKG_NAME="${PKG_NAME:-re-gu-trans-ctc}"
    MODEL_SOURCE_DEFAULT="$PACKAGE_ROOT/models/artifacts/gu-transformer-ctc-v5"
    MODEL_PACK_DEFAULT="$DIST/gujarati-model-pack-linux-ctc"
    CONFLICT_PKG="re-gu-trans-xlit"
    PLUGIN_SOURCE_DEFAULT="$PACKAGE_ROOT/native/gujarati-ctc-model-plugin"
    PKG_DESC="Gujarati roman-to-script transliteration for Rime (lexicon + QuickJS), with the compact gu-transformer-ctc-v5 neural model (sequence-level distilled from IndicXlit across the full training corpus, not just the long tail: 70.3% top-1 / 91.2% recall@6 held-out, ~2.5ms/query -- strictly more accurate than v4 at the same size and latency budget), fcitx5, and the Ori theme + Noto Serif Gujarati candidate font all installed as part of this package. On a system with a desktop session, installing this package enables Gujarati typing directly; otherwise run re-gu-trans-enable once as your user. Conflicts with re-gu-trans-xlit (same schema, higher-accuracy IndicXlit model) -- install one or the other."
    ;;
  *)
    echo "FAIL: MODEL_ARCH must be indicxlit or ctc (got: $MODEL_ARCH)" >&2
    exit 2
    ;;
esac
MODEL_SOURCE="${MODEL_SOURCE:-$MODEL_SOURCE_DEFAULT}"
PLUGIN_SOURCE="${PLUGIN_SOURCE:-$PLUGIN_SOURCE_DEFAULT}"

# TARGET_ARCH selects the CPU architecture this package targets: "x64"
# (default, nfpm arch amd64, Debian multiarch tuple x86_64-linux-gnu) or
# "arm64" (nfpm arch arm64, tuple aarch64-linux-gnu). Native, not cross:
# expects to run on a runner/host of that architecture, since it builds and
# links librime-qjs.so and the model plugin for whatever `cc`/`cmake` here
# actually target.
TARGET_ARCH="${TARGET_ARCH:-x64}"
case "$TARGET_ARCH" in
  x64) NFPM_ARCH="amd64"; MULTIARCH_TUPLE="x86_64-linux-gnu" ;;
  arm64) NFPM_ARCH="arm64"; MULTIARCH_TUPLE="aarch64-linux-gnu" ;;
  *) echo "FAIL: TARGET_ARCH must be x64 or arm64 (got: $TARGET_ARCH)" >&2; exit 2 ;;
esac
# This package is meant to be plug-and-play: the neural model pack and the
# fcitx5 theme/font default are always bundled in, not left as a separate
# optional download.
MODEL_PACK="${MODEL_PACK:-$MODEL_PACK_DEFAULT}"
THEME_CACHE="${THEME_CACHE:-$DIST/ori-fcitx5-theme}"

mkdir -p "$OUT_DIR" "$DIST/plugins"

if [[ ! -f "$PLUGIN_SO" ]]; then
  echo "Building librime-qjs.so ..."
  "$SCRIPT_DIR/build_librime_qjs.sh"
fi
require_file "$PLUGIN_SO"
"$PACKAGE_ROOT/scripts/package/verify_qjs_plugin.sh" "$PLUGIN_SO"

"$SCRIPT_DIR/../stage_payload.sh" "$PAYLOAD" linux

if [[ ! -d "$MODEL_PACK" ]]; then
  echo "Building $MODEL_ARCH neural model pack (MODEL_PACK not found at $MODEL_PACK) ..."
  ONNXRUNTIME_ROOT="${ONNXRUNTIME_ROOT:?ONNXRUNTIME_ROOT must point to ONNX Runtime 1.23.2 to build the bundled model pack}" \
  MODEL_SOURCE="$MODEL_SOURCE" \
  PLUGIN_SOURCE="$PLUGIN_SOURCE" \
  BUILD_DIR="$DIST/gujarati-model-build-linux-$MODEL_ARCH" \
  ASSEMBLY_DIR="$DIST/gujarati-model-assembly-linux-$MODEL_ARCH" \
  OUT_DIR="$MODEL_PACK" \
    "$SCRIPT_DIR/build_neural_model_pack.sh"
fi
"$PACKAGE_ROOT/scripts/package/validate_neural_model_pack.sh" "$MODEL_PACK"

if [[ ! -d "$THEME_CACHE/OriDark" ]]; then
  echo "Fetching Ori fcitx5 theme ..."
  rm -rf "$THEME_CACHE"
  git clone --depth 1 https://github.com/Reverier-Xu/Ori-fcitx5.git "$THEME_CACHE"
fi

rm -rf "$STAGE"
mkdir -p \
  "$STAGE/usr/lib/rime-plugins" \
  "$STAGE/usr/lib/$MULTIARCH_TUPLE/rime-plugins" \
  "$STAGE/usr/share/rime-data/js" \
  "$STAGE/usr/share/rime-data/gujarati-model" \
  "$STAGE/usr/share/fcitx5/themes" \
  "$STAGE/etc/xdg/fcitx5/conf" \
  "$STAGE/usr/share/re-gu-trans/snippets" \
  "$STAGE/usr/bin"

# Plugin (both common search paths)
cp -f "$PLUGIN_SO" "$STAGE/usr/lib/rime-plugins/librime-qjs.so"
cp -f "$PLUGIN_SO" "$STAGE/usr/lib/$MULTIARCH_TUPLE/rime-plugins/librime-qjs.so"

# Shared Rime data (schemas + JS loadable via sharedDataDir) — binary Tries
mkdir -p "$STAGE/usr/share/rime-data/js"
cp -f "$PAYLOAD/rime/gujarati.schema.yaml" "$STAGE/usr/share/rime-data/"
cp -f "$PAYLOAD/rime/js/"*.js "$STAGE/usr/share/rime-data/js/"
cp -f "$PAYLOAD/rime/js/"*.json "$STAGE/usr/share/rime-data/js/" 2>/dev/null || true
cp -f "$PAYLOAD/rime/js/"*.bin "$STAGE/usr/share/rime-data/js/"
if [[ -d "$PAYLOAD/rime/js/lm" ]]; then
  mkdir -p "$STAGE/usr/share/rime-data/js/lm"
  cp -f "$PAYLOAD/rime/js/lm/"* "$STAGE/usr/share/rime-data/js/lm/" 2>/dev/null || true
fi

# Vendor copy + enable helper
cp -a "$PAYLOAD/rime" "$STAGE/usr/share/re-gu-trans/"
cp -f "$PAYLOAD/rime/default.custom.yaml.snippet" "$STAGE/usr/share/re-gu-trans/snippets/" 2>/dev/null || true
cp -f "$PACKAGE_ROOT/packaging/linux/re-gu-trans-enable" "$STAGE/usr/bin/"
chmod 755 "$STAGE/usr/bin/re-gu-trans-enable"

# Neural model pack — placed under the shared Rime data dir's gujarati-model/
# subdirectory, which the native plugin's search path (neuralBridge.cc)
# checks before anything per-user, so it's found with zero user setup.
cp -a "$MODEL_PACK/." "$STAGE/usr/share/rime-data/gujarati-model/"

# Ori fcitx5 theme, system-wide for every user on the machine.
cp -r "$THEME_CACHE/OriDark" "$THEME_CACHE/OriLight" "$STAGE/usr/share/fcitx5/themes/"

# System-wide default candidate-panel theme/font (XDG_CONFIG_DIRS fallback);
# a user's own ~/.config/fcitx5/conf/classicui.conf still takes precedence.
cat > "$STAGE/etc/xdg/fcitx5/conf/classicui.conf" <<'EOF'
[Appearance]
Theme=OriDark
DarkTheme=OriDark
UseDarkThemeWhenSystemDefaultIsDark=False
Font="Noto Serif Gujarati,Noto Sans 11"
MenuFont="Noto Sans 10"
TrayFont="Sans 10"
PreferTextIcon=False
ShowLayoutNameInIcon=True
UseInputMethodLanguageToDisplayText=True
WheelHasEffect=True
PerScreenDPI=False
Vertical Candidate List=False
EOF

# STAGE_ONLY=1 stops here: used by the Arch PKGBUILD (packaging/arch/), which
# only wants the staged $STAGE tree to repackage itself -- it doesn't need
# nfpm's .deb/.rpm output, and validate_archive.sh's .rpm check requires
# rpm2cpio, which isn't part of a stock Arch build environment.
if [[ "${STAGE_ONLY:-0}" == "1" ]]; then
  echo "STAGE_ONLY=1: staged tree ready at $STAGE, skipping nfpm/.deb/.rpm"
  exit 0
fi

# Generate nfpm config with version/name/description/conflict substituted
TMP_NFPM="$(mktemp)"
sed \
  -e "s/__VERSION__/${VERSION}/g" \
  -e "s/__PKGNAME__/${PKG_NAME}/g" \
  -e "s#__PKGDESC__#${PKG_DESC}#g" \
  -e "s/__CONFLICTS__/${CONFLICT_PKG}/g" \
  -e "s/__ARCH__/${NFPM_ARCH}/g" \
  -e "s/__MULTIARCH_TUPLE__/${MULTIARCH_TUPLE}/g" \
  "$NFPM_CONFIG" > "$TMP_NFPM"

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
for package in "$OUT_DIR"/*.deb "$OUT_DIR"/*.rpm; do
  [[ -f "$package" ]] && "$SCRIPT_DIR/../validate_archive.sh" "$package"
done
