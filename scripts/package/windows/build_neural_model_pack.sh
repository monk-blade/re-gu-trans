#!/usr/bin/env bash
# Build the Windows x64 optional Gujarati ONNX model pack under Git Bash/MSVC.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ORT_ROOT="${ONNXRUNTIME_ROOT:?ONNXRUNTIME_ROOT must point to ONNX Runtime 1.23.2}"
SOURCE="${MODEL_SOURCE:-$ROOT/models/artifacts/gu-indicxlit-v1}"
BUILD="${BUILD_DIR:-$ROOT/dist/gujarati-model-build-windows}"
ASSEMBLY="${ASSEMBLY_DIR:-$ROOT/dist/gujarati-model-assembly-windows}"
OUT="${OUT_DIR:-$ROOT/dist/gujarati-model-pack-windows}"

test "$(tr -d '\r\n' < "$ORT_ROOT/VERSION_NUMBER")" = "1.23.2" || {
  echo "FAIL: ONNX Runtime 1.23.2 is required" >&2
  exit 1
}
# Ninja + the MSVC env vars set up by ilammy/msvc-dev-cmd (INCLUDE/LIB/PATH
# pointing at cl.exe) avoids pinning to a specific Visual Studio generator
# version, which breaks whenever a GitHub-hosted windows-latest image ships
# a newer VS release than "17 2022".
cmake -S "$ROOT/native/gujarati-model-plugin" -B "$BUILD" \
  -G Ninja -DCMAKE_BUILD_TYPE=Release -DONNXRUNTIME_ROOT="$ORT_ROOT"
cmake --build "$BUILD" --parallel 2
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
