#!/usr/bin/env python3
"""Recompute training-manifest.json's model_sha256 for the ONNX files that
actually exist on disk right now.

A fresh export in a different torch/onnxruntime build than the one used to
produce the committed artifact is functionally identical but not always
byte-identical, so validate_neural_model_pack.sh's checksum check needs
checksums matching whatever THIS run actually produced.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "models" / "artifacts" / "gu-indicxlit-v1"
MODEL_FILES = ("indicxlit_encoder.onnx", "indicxlit_decoder_v2.onnx")


def main() -> int:
    manifest_path = ARTIFACT / "training-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["model_sha256"] = {
        name: hashlib.sha256((ARTIFACT / name).read_bytes()).hexdigest() for name in MODEL_FILES
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"refreshed {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
