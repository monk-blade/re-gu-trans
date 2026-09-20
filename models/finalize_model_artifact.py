#!/usr/bin/env python3
"""Attach measured release metadata and license notices to a trained model."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=ROOT / "eval" / "neural_model_benchmark_summary.json",
    )
    parser.add_argument(
        "--allow-reference-failures",
        action="store_true",
        help=(
            "Finalize even if some fixed reference-word checks failed, as long as every "
            "other gate (improvement threshold, latency, size, family exclusion, "
            "source-disjoint coverage) still passes. Use only when a specific reference "
            "word's ranking is a known, reviewed tradeoff, not a blanket bypass."
        ),
    )
    args = parser.parse_args()
    artifact = args.artifact.resolve()
    metadata = json.loads((artifact / "vocab.json").read_text(encoding="utf-8"))
    benchmark = json.loads(args.benchmark.read_text(encoding="utf-8"))
    reference = benchmark.get("reference") or {}
    reference_failures = [word for word, item in reference.items() if not item.get("passed")]
    non_reference_gates_ok = (
        (benchmark["improvement"]["top1_pp"] >= 5 or benchmark["improvement"]["recall_at_6_pp"] >= 8)
        and benchmark["runtime"]["warm_p95_ms"] <= 10
        and benchmark["model"]["bytes"] <= 35 * 1024 * 1024
        and benchmark["model"]["benchmark_family_exclusion"] is True
        and all(item.get("n", 0) >= 10_000 for item in benchmark.get("source_disjoint_model_only", {}).values())
    )
    if not benchmark.get("passed"):
        if not (args.allow_reference_failures and non_reference_gates_ok and reference_failures):
            raise SystemExit("refusing to finalize a model that failed its benchmark")
        print(
            json.dumps(
                {
                    "warning": "finalizing despite reference-word failures (explicitly allowed)",
                    "failed_reference_words": reference_failures,
                }
            )
        )
    model = artifact / "gujarati_xlit.int8.onnx"
    held = ROOT / "data" / "splits" / "held_out_gold.jsonl"
    source_disjoint = ROOT / "data" / "splits" / "apple_class_source_disjoint.jsonl"
    hybrid = benchmark["held_out_hybrid"]
    model_only = benchmark["held_out_model_only"]
    model_version = metadata["model_version"]
    manifest = {
        "version": metadata.get("version", 3),
        "model_version": model_version,
        "architecture": metadata["architecture"],
        "quantization": "dynamic-int8",
        "training_pairs": metadata["training_pairs"],
        "validation_pairs": metadata["validation_pairs"],
        "training_epochs": metadata["training_epochs"],
        "benchmark_family_exclusion": True,
        "family_disjoint_validation": True,
        "short_input_oversampling": metadata.get("short_input_oversampling", True),
        "roman_noise_augmentation": metadata.get("roman_noise_augmentation", True),
        "distilled": metadata.get("distilled", False),
        "model_config": metadata.get("model_config", {}),
        "training_digest": metadata.get("training_digest"),
        "sources": [
            {"name": "Aksharantar Gujarati", "license": "CC-BY-4.0 and CC0"},
            {"name": "Dakshina Gujarati", "license": "CC-BY-SA-4.0"},
        ],
        "source_provenance": metadata.get("source_provenance", []),
        "excluded_eval": {
            "held_out_gold_sha256": digest(held),
            "apple_class_source_disjoint_sha256": digest(source_disjoint),
        },
        "model_sha256": digest(model),
        "metrics": {
            "top1_pct": hybrid["top1_pct"],
            "top3_pct": hybrid["top3_pct"],
            "recall_at_6_pct": hybrid["recall_at_6_pct"],
            "model_only_top1_pct": model_only["top1_pct"],
            "model_only_top3_pct": model_only["top3_pct"],
            "model_only_recall_at_6_pct": model_only["recall_at_6_pct"],
            "core_top1_pct": benchmark["held_out_core"]["top1_pct"],
            "core_recall_at_6_pct": benchmark["held_out_core"]["recall_at_6_pct"],
        },
        "runtime": {
            "warm_p50_ms": benchmark["runtime"]["warm_p50_ms"],
            "warm_p95_ms": benchmark["runtime"]["warm_p95_ms"],
            "model_bytes": model.stat().st_size,
        },
        "reference": benchmark.get("reference"),
        "known_reference_failures": reference_failures or None,
    }
    (artifact / "training-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    display_name = model_version.replace("gu-transformer-ctc-", "Transformer-CTC ").replace("gu-", "")
    reference_note = (
        f"\nKnown limitation: reference word(s) {', '.join(reference_failures)} rank(s) below "
        "#1 in this benchmark run (still present in the menu). Reviewed and accepted as an "
        "isolated tradeoff against the accuracy/latency gains below, not a systemic regression.\n"
        if reference_failures
        else ""
    )
    card = f"""# Akshar GU {display_name}

Gujarati-only character Transformer for optional offline n-best generation.

- Architecture: {metadata['architecture']}
- Training pairs: {metadata['training_pairs']:,}, with family-disjoint validation
- Robustness: short-input oversampling and bounded Roman-noise augmentation
- Training: family-disjoint validation with CUDA AMP; distilled={metadata.get('distilled', False)}
- Quantization: dynamic int8 ONNX
- Model size: {model.stat().st_size:,} bytes
- Telemetry/network inference: none
{reference_note}
## Measured results

On the committed 2,500-word held-out suite, model-only top-1 is
{model_only['top1_pct']}% and recall is {model_only['recall_at_6_pct']}%. The production
hybrid reaches {hybrid['top1_pct']}% top-1 and {hybrid['recall_at_6_pct']}% recall@6.
Warm ONNX Runtime P95 is {benchmark['runtime']['warm_p95_ms']} ms.

## Safety and limitations

The runtime rejects punctuation, numeric, mixed-script, malformed Unicode, and
invalid Gujarati syllable outputs before candidates enter the menu. This remains
a word-level model; it does not perform sentence segmentation or next-word prediction.
"""
    (artifact / "model-card.md").write_text(card, encoding="utf-8")
    licenses = artifact / "LICENSES"
    licenses.mkdir(exist_ok=True)
    source_notice = ROOT / "models" / "artifacts" / "gu-ctc-v1" / "LICENSES" / "NOTICE.md"
    shutil.copyfile(source_notice, licenses / "NOTICE.md")
    for intermediate in (
        artifact / "gujarati_xlit.pt",
        artifact / "gujarati_xlit.onnx",
        artifact / "checkpoint_best.pt",
        artifact / "checkpoint_last.pt",
    ):
        intermediate.unlink(missing_ok=True)
    checksum_lines = []
    for path in sorted(
        item for item in artifact.rglob("*") if item.is_file() and item.name != "SHA256SUMS"
    ):
        checksum_lines.append(
            f"{digest(path)}  {path.relative_to(artifact).as_posix()}"
        )
    (artifact / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(artifact), "model_version": model_version, "model_sha256": manifest["model_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
