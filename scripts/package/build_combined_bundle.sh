#!/usr/bin/env bash
# Build a platform-specific self-contained core + model installer archive.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"
PLATFORM="${1:?platform: linux|macos|windows}"
CORE_DIR="${2:?core package/payload directory}"
MODEL_DIR="${3:?validated model-pack directory}"
OUT_ARCHIVE="${4:?output archive}"
VERSION="${5:-$(resolve_version)}"
STAGE="${OUT_ARCHIVE}.stage"

"$SCRIPT_DIR/stage_combined_bundle.sh" "$PLATFORM" "$CORE_DIR" "$MODEL_DIR" "$STAGE" "$VERSION"
mkdir -p "$(dirname "$OUT_ARCHIVE")"
rm -f "$OUT_ARCHIVE"
case "$PLATFORM" in
  linux) tar -czf "$OUT_ARCHIVE" -C "$STAGE" . ;;
  macos|windows) zip_dir_contents "$STAGE" "$OUT_ARCHIVE" ;;
  *) echo "FAIL: unsupported platform $PLATFORM" >&2; exit 2 ;;
esac
rm -rf "$STAGE"
echo "COMBINED_BUNDLE_BUILT platform=$PLATFORM archive=$OUT_ARCHIVE"
