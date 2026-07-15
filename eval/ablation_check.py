#!/usr/bin/env python3
"""Measure one policy-owned generation family against production JavaScript."""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from held_out_agree import FROZEN_GOLD, SAMPLE_N, SEED
from production_rank import top_six_many

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "ablation_summary.json"


def metrics(rows: list[tuple[str, str]], menus: list[list[str]]) -> dict[str, float | int]:
    top1 = top3 = recall6 = 0
    ndcg = 0.0
    for (_roman, native), menu in zip(rows, menus, strict=True):
        if menu and menu[0] == native:
            top1 += 1
        if native in menu[:3]:
            top3 += 1
        if native in menu[:6]:
            recall6 += 1
            ndcg += 1.0 / math.log2(menu.index(native) + 2)
    count = len(rows)
    return {
        "evaluated": count,
        "top1_pct": round(100 * top1 / count, 3),
        "top3_pct": round(100 * top3 / count, 3),
        "recall_at_6_pct": round(100 * recall6 / count, 3),
        "ndcg_at_6": round(ndcg / count, 5),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "families",
        nargs="*",
        default=["conjunct_virama", "plural_postpositions"],
    )
    args = parser.parse_args()
    rows = []
    for line in FROZEN_GOLD.read_text(encoding="utf-8").splitlines():
        if line:
            row = json.loads(line)
            rows.append((str(row["roman"]).lower(), str(row["native"])))
    if len(rows) > SAMPLE_N:
        rows = random.Random(SEED).sample(rows, SAMPLE_N)

    romans = [roman for roman, _ in rows]
    enabled = metrics(rows, top_six_many(romans))
    families = []
    for family in args.families:
        disabled = metrics(rows, top_six_many(romans, disable_family=family))
        recall_delta = round(
            float(enabled["recall_at_6_pct"]) - float(disabled["recall_at_6_pct"]), 3
        )
        top1_delta = round(float(enabled["top1_pct"]) - float(disabled["top1_pct"]), 3)
        accepted = recall_delta >= 0.25 or top1_delta >= 0.15
        families.append({
            "family": family,
            "disabled": disabled,
            "delta_percentage_points": {
                "top1": top1_delta,
                "recall_at_6": recall_delta,
            },
            "accepted": accepted,
        })
    report = {
        "ranker": "production-javascript-trie",
        "enabled": enabled,
        "families": families,
        "threshold": {"top1": 0.15, "recall_at_6": 0.25},
        "accepted": all(item["accepted"] for item in families),
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
