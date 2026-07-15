#!/usr/bin/env python3
"""Fit a word-independent pairwise ranker for Gujarati evidence-tier candidates."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.gujarati_ctc import GujaratiCtcOnnx
from models.train_gujarati_ctc import load_pairs
from models.train_gujarati_transformer import split_pairs

RUNNER = ROOT / "eval" / "js_production_runner.mjs"
FEATURES = (
    "base_score", "log_weight", "log_evidence", "transform_cost",
    "neural_relative", "neural_seen", "neural_rank", "model_core_agreement",
    "source_strict", "source_fuzzy", "source_phonetic", "source_morphology",
    "native_length_ratio",
)


def family_bucket(roman: str) -> int:
    return int(hashlib.sha256(roman.encode()).hexdigest()[:8], 16) % 5


def candidate_vector(candidate: dict) -> np.ndarray:
    values = candidate.get("rankFeatures") or {}
    return np.asarray([float(values.get(name, 0)) for name in FEATURES], dtype=np.float64)


def production_rows(groups: dict[str, set[str]], model: GujaratiCtcOnnx) -> list[dict]:
    with tempfile.TemporaryDirectory(prefix="akshar-ranker-") as temp:
        root = Path(temp)
        source = root / "input.jsonl"
        output = root / "output.jsonl"
        fixture_path = root / "neural.json"
        source.write_text(
            "".join(json.dumps({"roman": roman}) + "\n" for roman in groups),
            encoding="utf-8",
        )
        fixtures = {}
        version = str(model.metadata.get("model_version") or "unknown")
        for roman in groups:
            candidates = model.nbest(roman, 4, 8)
            best = candidates[0].log_prob if candidates else 0
            fixtures[roman] = [
                {"native": item.native, "logProb": item.log_prob - best, "modelVersion": version}
                for item in candidates
            ]
        fixture_path.write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env["NEURAL_FIXTURES"] = str(fixture_path)
        env["DEBUG_RANK"] = "1"
        process = subprocess.run(
            ["node", str(RUNNER), "trie", str(source), str(output)],
            cwd=ROOT, env=env, text=True, capture_output=True, check=False,
        )
        if process.returncode:
            raise RuntimeError(process.stdout + process.stderr)
        return [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line]


def comparisons(rows: list[dict], groups: dict[str, set[str]], bucket: int):
    pairs = []
    candidate_values = []
    usable = 0
    baseline = 0
    for row in rows:
        roman = row["roman"]
        if family_bucket(roman) != bucket:
            continue
        accepted = groups[roman]
        candidates = [item for item in row.get("debug") or [] if item.get("tier") == 1]
        positives = [item for item in candidates if item["text"] in accepted]
        negatives = [item for item in candidates if item["text"] not in accepted]
        if not positives or not negatives:
            continue
        usable += 1
        baseline += int(bool(row.get("top6")) and row["top6"][0] in accepted)
        vectors = {item["text"]: candidate_vector(item) for item in candidates}
        candidate_values.extend(vectors.values())
        for positive in positives:
            for negative in negatives:
                diff = vectors[positive["text"]] - vectors[negative["text"]]
                pairs.append((diff, 1.0))
                pairs.append((-diff, 0.0))
    return pairs, candidate_values, usable, baseline


def fit(train_pairs, raw_values, iterations: int, learning_rate: float):
    raw = np.vstack(raw_values)
    mean = raw.mean(axis=0)
    scale = raw.std(axis=0)
    scale[scale < 1e-6] = 1.0
    x = np.vstack([pair[0] / scale for pair in train_pairs])
    y = np.asarray([pair[1] for pair in train_pairs], dtype=np.float64)
    weights = np.zeros(x.shape[1], dtype=np.float64)
    bias = 0.0
    for _ in range(iterations):
        logits = np.clip(x @ weights + bias, -30, 30)
        probabilities = 1.0 / (1.0 + np.exp(-logits))
        error = probabilities - y
        weights -= learning_rate * ((x.T @ error) / len(y) + 1e-3 * weights)
        bias -= learning_rate * float(error.mean())
    return mean, scale, weights, bias


def evaluate(rows, groups, bucket, mean, scale, weights, bias):
    usable = 0
    baseline = 0
    ranked = 0
    for row in rows:
        roman = row["roman"]
        if family_bucket(roman) != bucket:
            continue
        accepted = groups[roman]
        candidates = [item for item in row.get("debug") or [] if item.get("tier") == 1]
        if not candidates or not any(item["text"] in accepted for item in candidates):
            continue
        usable += 1
        baseline += int(row["top6"][0] in accepted)
        best = max(
            candidates,
            key=lambda item: float(((candidate_vector(item) - mean) / scale) @ weights + bias),
        )
        ranked += int(best["text"] in accepted)
    return {"usable": usable, "baseline_top1": baseline, "ranker_top1": ranked}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=ROOT / "models/artifacts/gu-transformer-ctc-v2")
    parser.add_argument("--max-romans", type=int, default=8000)
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument("--output", type=Path, default=ROOT / "eval/hybrid_ranker_coefficients.json")
    args = parser.parse_args()

    _train, validation = split_pairs(load_pairs(600_000, 29))
    grouped: dict[str, set[str]] = defaultdict(set)
    for roman, native in validation:
        grouped[roman].add(native)
    groups = dict(list(sorted(grouped.items()))[: args.max_romans])
    rows = production_rows(groups, GujaratiCtcOnnx(args.model_dir))
    train_pairs, raw_values, train_usable, train_baseline = comparisons(rows, groups, bucket=0)
    # Four hash buckets train; bucket zero is held back. Rebuild the training set explicitly.
    train_pairs = []
    raw_values = []
    train_usable = train_baseline = 0
    for bucket in (1, 2, 3, 4):
        pairs, values, usable, baseline = comparisons(rows, groups, bucket)
        train_pairs.extend(pairs)
        raw_values.extend(values)
        train_usable += usable
        train_baseline += baseline
    if not train_pairs:
        raise SystemExit("no pairwise training examples")
    mean, scale, weights, bias = fit(
        train_pairs, raw_values, args.iterations, args.learning_rate
    )
    validation_report = evaluate(rows, groups, 0, mean, scale, weights, bias)
    payload = {
        "version": 1,
        "candidate_only": True,
        "approved_for_runtime": False,
        "features": list(FEATURES),
        "bias": round(float(bias), 8),
        "weights": {name: round(float(value), 8) for name, value in zip(FEATURES, weights, strict=True)},
        "mean": {name: round(float(value), 8) for name, value in zip(FEATURES, mean, strict=True)},
        "scale": {name: round(float(value), 8) for name, value in zip(FEATURES, scale, strict=True)},
        "training": {
            "family_disjoint": True,
            "romans": len(groups),
            "usable": train_usable,
            "pair_examples": len(train_pairs),
            "baseline_top1": train_baseline,
        },
        "validation": validation_report,
    }
    payload["passed"] = (
        validation_report["usable"] >= 100 and
        validation_report["ranker_top1"] > validation_report["baseline_top1"]
    )
    payload["development_gate_passed"] = payload["passed"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
