#!/usr/bin/env bash
# Build and stage the optional macOS Gujarati model pack against pinned ORT.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ORT_ROOT="${ONNXRUNTIME_ROOT:?ONNXRUNTIME_ROOT must point to ONNX Runtime 1.23.2}"
SOURCE="${MODEL_SOURCE:-$ROOT/models/artifacts/gu-transformer-ctc-v3}"
BUILD="${BUILD_DIR:-$ROOT/dist/gujarati-model-build-macos}"
ASSEMBLY="${ASSEMBLY_DIR:-$ROOT/dist/gujarati-model-assembly-macos}"
OUT="${OUT_DIR:-$ROOT/dist/gujarati-model-pack-macos}"

test "$(cat "$ORT_ROOT/VERSION_NUMBER")" = "1.23.2" || {
  echo "FAIL: ONNX Runtime 1.23.2 is required" >&2
  exit 1
}
cmake -S "$ROOT/native/gujarati-model-plugin" -B "$BUILD" \
  -DONNXRUNTIME_ROOT="$ORT_ROOT" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD" --config Release --parallel 2

rm -rf "$ASSEMBLY"
mkdir -p "$ASSEMBLY"
cp -R "$SOURCE/." "$ASSEMBLY/"
cp "$BUILD/librime-gujarati-model.dylib" "$ASSEMBLY/"
cp "$ORT_ROOT/lib/libonnxruntime.1.23.2.dylib" "$ASSEMBLY/libonnxruntime.dylib"
strip -x "$ASSEMBLY/libonnxruntime.dylib"
install_name_tool -change \
  @rpath/libonnxruntime.1.23.2.dylib \
  @loader_path/libonnxruntime.dylib \
  "$ASSEMBLY/librime-gujarati-model.dylib"
codesign --force --sign - "$ASSEMBLY/libonnxruntime.dylib" "$ASSEMBLY/librime-gujarati-model.dylib"

NEURAL_PLUGIN="$ASSEMBLY/librime-gujarati-model.dylib" \
ONNXRUNTIME_LIBRARY="$ASSEMBLY/libonnxruntime.dylib" \
  "$ROOT/scripts/package/stage_neural_model_pack.sh" "$ASSEMBLY" "$OUT"
"$ROOT/scripts/package/validate_neural_model_pack.sh" "$OUT"
