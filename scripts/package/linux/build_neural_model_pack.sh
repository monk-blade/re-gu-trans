#!/usr/bin/env bash
# Build the Linux x86_64 optional Gujarati ONNX model pack.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ORT_ROOT="${ONNXRUNTIME_ROOT:?ONNXRUNTIME_ROOT must point to ONNX Runtime 1.23.2}"
SOURCE="${MODEL_SOURCE:-$ROOT/models/artifacts/gu-ctc-v1}"
BUILD="${BUILD_DIR:-$ROOT/dist/gujarati-model-build-linux}"
ASSEMBLY="${ASSEMBLY_DIR:-$ROOT/dist/gujarati-model-assembly-linux}"
OUT="${OUT_DIR:-$ROOT/dist/gujarati-model-pack-linux}"

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
cp "$BUILD/librime-gujarati-model.so" "$ASSEMBLY/"
cp -L "$ORT_ROOT/lib/libonnxruntime.so.1" "$ASSEMBLY/libonnxruntime.so.1"
strip "$ASSEMBLY/librime-gujarati-model.so" "$ASSEMBLY/libonnxruntime.so.1"
NEURAL_PLUGIN="$ASSEMBLY/librime-gujarati-model.so" \
ONNXRUNTIME_LIBRARY="$ASSEMBLY/libonnxruntime.so.1" \
  "$ROOT/scripts/package/stage_neural_model_pack.sh" "$ASSEMBLY" "$OUT"
"$ROOT/scripts/package/validate_neural_model_pack.sh" "$OUT"
