#!/usr/bin/env python3
"""A/B benchmark: in-house Gujarati CTC model vs. AI4Bharat IndicXlit.

Runs both models over the same held-out gold set and reports top1/top3/
recall@6 accuracy plus warm per-query latency, so the two can be compared
on equal footing. IndicXlit's autoregressive beam search is far slower on
CPU, so its accuracy pass defaults to a smaller sample (--indicxlit-limit)
while the CTC model runs over the full set.

Must run under the venv with fairseq/torch installed:
    .venv-indicxlit/bin/python3 eval/indicxlit_ab_benchmark.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
HELD = ROOT / "data" / "splits" / "held_out_gold.jsonl"
OUT = ROOT / "eval" / "indicxlit_ab_summary.json"


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


def evaluate(model, rows: list[dict], count: int = 6, beam_width: int = 8) -> tuple[dict, list[float]]:
    menus: list[list[str]] = []
    timings: list[float] = []
    for row in rows:
        started = time.perf_counter()
        candidates = model.nbest(row["roman"], count, beam_width)
        timings.append((time.perf_counter() - started) * 1000)
        menus.append([item.native for item in candidates])
    return metrics(rows, menus), timings


def runtime_stats(timings: list[float]) -> dict:
    ordered = sorted(timings)
    n = len(ordered)
    return {
        "queries": n,
        "warm_p50_ms": round(ordered[n // 2], 3) if n else None,
        "warm_p95_ms": round(ordered[int(n * 0.95)] if n else 0, 3) if n else None,
        "mean_ms": round(sum(ordered) / n, 3) if n else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ctc-model-dir", type=Path, default=ROOT / "models" / "artifacts" / "gu-transformer-ctc-v3")
    parser.add_argument("--indicxlit-release-dir", type=Path, default=ROOT / "data" / "external" / "indicxlit" / "release")
    parser.add_argument("--indicxlit-limit", type=int, default=500, help="IndicXlit beam search is slow on CPU; sample this many held-out rows")
    parser.add_argument("--warmup", type=int, default=5)
    args = parser.parse_args()

    held = [json.loads(line) for line in HELD.read_text(encoding="utf-8").splitlines() if line]

    from models.gujarati_ctc import GujaratiCtcOnnx

    ctc_model = GujaratiCtcOnnx(args.ctc_model_dir)
    for row in held[: args.warmup]:
        ctc_model.nbest(row["roman"], 6, 8)
    ctc_metrics, ctc_timings = evaluate(ctc_model, held)
    ctc_runtime = runtime_stats(ctc_timings)

    from models.indicxlit_fairseq import IndicXlitFairseq

    indicxlit_model = IndicXlitFairseq(args.indicxlit_release_dir)
    indicxlit_rows = held[: args.indicxlit_limit]
    for row in indicxlit_rows[: args.warmup]:
        indicxlit_model.nbest(row["roman"], 6, 8)
    indicxlit_metrics, indicxlit_timings = evaluate(indicxlit_model, indicxlit_rows)
    indicxlit_runtime = runtime_stats(indicxlit_timings)

    payload = {
        "report": "indicxlit_ab_benchmark",
        "held_out_size": len(held),
        "gu_transformer_ctc_v3": {
            "accuracy": ctc_metrics,
            "runtime": ctc_runtime,
        },
        "indicxlit_fairseq": {
            "accuracy": indicxlit_metrics,
            "runtime": indicxlit_runtime,
            "sampled_n": len(indicxlit_rows),
            "note": "sampled subset of held_out_gold; beam search is CPU-bound and much slower per query",
        },
        "speedup_ctc_over_indicxlit_p50": (
            round(indicxlit_runtime["warm_p50_ms"] / ctc_runtime["warm_p50_ms"], 1)
            if ctc_runtime["warm_p50_ms"]
            else None
        ),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
