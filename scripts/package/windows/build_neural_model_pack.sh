#!/usr/bin/env bash
# Build the Windows x64 optional Gujarati ONNX model pack under Git Bash/MSVC.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ORT_ROOT="${ONNXRUNTIME_ROOT:?ONNXRUNTIME_ROOT must point to ONNX Runtime 1.23.2}"
SOURCE="${MODEL_SOURCE:-$ROOT/models/artifacts/gu-ctc-v1}"
BUILD="${BUILD_DIR:-$ROOT/dist/gujarati-model-build-windows}"
ASSEMBLY="${ASSEMBLY_DIR:-$ROOT/dist/gujarati-model-assembly-windows}"
OUT="${OUT_DIR:-$ROOT/dist/gujarati-model-pack-windows}"

test "$(tr -d '\r\n' < "$ORT_ROOT/VERSION_NUMBER")" = "1.23.2" || {
  echo "FAIL: ONNX Runtime 1.23.2 is required" >&2
  exit 1
}
cmake -S "$ROOT/native/gujarati-model-plugin" -B "$BUILD" \
  -G "Visual Studio 17 2022" -A x64 -DONNXRUNTIME_ROOT="$ORT_ROOT"
cmake --build "$BUILD" --config Release --parallel 2
PLUGIN="$(find "$BUILD" -type f -name 'rime-gujarati-model.dll' | head -1)"
test -n "$PLUGIN"
rm -rf "$ASSEMBLY"
mkdir -p "$ASSEMBLY"
cp -R "$SOURCE/." "$ASSEMBLY/"
cp "$PLUGIN" "$ASSEMBLY/"
cp "$ORT_ROOT/lib/onnxruntime.dll" "$ASSEMBLY/"
NEURAL_PLUGIN="$ASSEMBLY/rime-gujarati-model.dll" \
ONNXRUNTIME_LIBRARY="$ASSEMBLY/onnxruntime.dll" \
  "$ROOT/scripts/package/stage_neural_model_pack.sh" "$ASSEMBLY" "$OUT"
"$ROOT/scripts/package/validate_neural_model_pack.sh" "$OUT"
