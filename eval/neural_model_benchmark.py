#!/usr/bin/env python3
"""Measure the compact ONNX model and its actual production-JS hybrid merge."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from production_rank import top_six_many

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HELD = ROOT / "data" / "splits" / "held_out_gold.jsonl"
SOURCE_DISJOINT = ROOT / "data" / "splits" / "apple_class_source_disjoint.jsonl"
RUNNER = ROOT / "eval" / "js_production_runner.mjs"
OUT = ROOT / "eval" / "neural_model_benchmark_summary.json"


def metrics(rows: list[dict], menus: list[list[str]]) -> dict:
    n = len(rows)
    top1 = sum(bool(menu) and menu[0] == row["native"] for row, menu in zip(rows, menus, strict=True))
    top3 = sum(row["native"] in menu[:3] for row, menu in zip(rows, menus, strict=True))
    recall = sum(row["native"] in menu[:6] for row, menu in zip(rows, menus, strict=True))
    return {
        "n": n,
        "top1_pct": round(100 * top1 / n, 2) if n else 0,
        "top3_pct": round(100 * top3 / n, 2) if n else 0,
        "recall_at_6_pct": round(100 * recall / n, 2) if n else 0,
    }


def metrics_by_length(rows: list[dict], menus: list[list[str]]) -> dict:
    buckets = {"1-3": [], "4-6": [], "7-10": [], "11-14": [], "15+": []}
    for row, menu in zip(rows, menus, strict=True):
        length = len(row["roman"])
        key = "1-3" if length <= 3 else "4-6" if length <= 6 else "7-10" if length <= 10 else "11-14" if length <= 14 else "15+"
        buckets[key].append((row, menu))
    return {
        key: metrics([row for row, _menu in items], [menu for _row, menu in items])
        for key, items in buckets.items()
    }


def hybrid_menus(rows: list[dict], fixtures: dict[str, list[dict]]) -> list[list[str]]:
    with tempfile.TemporaryDirectory(prefix="akshar-neural-benchmark-") as temp:
        root = Path(temp)
        source = root / "input.jsonl"
        output = root / "output.jsonl"
        fixture_path = root / "neural.json"
        source.write_text(
            "".join(json.dumps({"roman": row["roman"]}) + "\n" for row in rows), encoding="utf-8"
        )
        fixture_path.write_text(json.dumps(fixtures, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env["NEURAL_FIXTURES"] = str(fixture_path)
        process = subprocess.run(
            ["node", str(RUNNER), "trie", str(source), str(output)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode:
            raise RuntimeError(process.stdout + process.stderr)
        return [
            json.loads(line)["top6"]
            for line in output.read_text(encoding="utf-8").splitlines()
            if line
        ]


def evaluate(model, rows: list[dict]) -> tuple[dict, dict[str, list[dict]], list[float]]:
    fixtures: dict[str, list[dict]] = {}
    model_menus = []
    timings = []
    for row in rows:
        started = time.perf_counter()
        candidates = model.nbest(row["roman"], 4, 8)
        timings.append((time.perf_counter() - started) * 1000)
        best = candidates[0].log_prob if candidates else 0.0
        model_version = str(model.metadata.get("model_version") or "unknown")
        fixtures[row["roman"]] = [
            {"native": item.native, "logProb": item.log_prob - best, "modelVersion": model_version}
            for item in candidates
        ]
        model_menus.append([item.native for item in candidates])
    return metrics(rows, model_menus), fixtures, timings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-dir", type=Path, default=ROOT / "models" / "artifacts" / "gu-transformer-ctc-v3"
    )
    parser.add_argument("--source-disjoint-limit-per-source", type=int, default=10_000)
    args = parser.parse_args()
    from models.gujarati_ctc import GujaratiCtcOnnx

    model = GujaratiCtcOnnx(args.model_dir)
    held = [json.loads(line) for line in HELD.read_text(encoding="utf-8").splitlines() if line]
    source_rows = [
        json.loads(line)
        for line in SOURCE_DISJOINT.read_text(encoding="utf-8").splitlines()
        if line
    ]
    by_source = {
        source: [row for row in source_rows if row.get("source") == source][
            : args.source_disjoint_limit_per_source
        ]
        for source in ("aksharantar", "dakshina")
    }
    held_model, held_fixtures, held_times = evaluate(model, held)
    source_metrics = {}
    source_times = []
    for source, rows in by_source.items():
        source_metric, _source_fixtures, timings = evaluate(model, rows)
        source_metrics[source] = source_metric
        source_times.extend(timings)
    core_menus = top_six_many([row["roman"] for row in held])
    hybrid = metrics(held, hybrid_menus(held, held_fixtures))
    core = metrics(held, core_menus)
    reference_rows = [
        {"roman": "yas", "native": "યસ"},
        {"roman": "chalshe", "native": "ચાલશે"},
        {"roman": "ko", "native": "કો"},
        {"roman": "to", "native": "તો"},
        {"roman": "wah", "native": "વાહ"},
        {"roman": "bagicho", "native": "બગીચો"},
    ]
    _reference_model, reference_fixtures, _reference_times = evaluate(model, reference_rows)
    reference_menus = hybrid_menus(reference_rows, reference_fixtures)
    reference = {
        row["roman"]: {
            "expected": row["native"],
            "menu": menu,
            "passed": bool(menu and menu[0] == row["native"]),
        }
        for row, menu in zip(reference_rows, reference_menus, strict=True)
    }
    timings = sorted(held_times + source_times)
    improvement = {
        "top1_pp": round(hybrid["top1_pct"] - core["top1_pct"], 2),
        "recall_at_6_pp": round(hybrid["recall_at_6_pct"] - core["recall_at_6_pct"], 2),
    }
    payload = {
        "report": "neural_model_benchmark",
        "model": {
            "architecture": model.metadata.get("architecture"),
            "training_pairs": model.metadata.get("training_pairs"),
            "benchmark_family_exclusion": model.metadata.get("benchmark_family_exclusion"),
            "bytes": (args.model_dir / "gujarati_xlit.int8.onnx").stat().st_size,
        },
        "held_out_model_only": held_model,
        "held_out_model_by_length": metrics_by_length(
            held,
            [[item.native for item in model.nbest(row["roman"], 6, 8)] for row in held],
        ),
        "source_disjoint_model_only": source_metrics,
        "held_out_core": core,
        "held_out_hybrid": hybrid,
        "improvement": improvement,
        "reference": reference,
        "runtime": {
            "queries": len(timings),
            "warm_p50_ms": round(timings[len(timings) // 2], 3),
            "warm_p95_ms": round(timings[int(len(timings) * 0.95)], 3),
        },
    }
    payload["passed"] = bool(
        (improvement["top1_pp"] >= 5 or improvement["recall_at_6_pp"] >= 8)
        and payload["runtime"]["warm_p95_ms"] <= 10
        and payload["model"]["bytes"] <= 35 * 1024 * 1024
        and payload["model"]["benchmark_family_exclusion"] is True
        and all(item["passed"] for item in reference.values())
        and all(
            item.get("n", 0) >= min(args.source_disjoint_limit_per_source, 10_000)
            for item in source_metrics.values()
        )
    )
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
