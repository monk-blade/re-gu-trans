#!/usr/bin/env python3
"""Held-out diagnostic: missing vs below-6 vs wrong-order."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import rank_offline as ro  # noqa: E402
from production_rank import top_six_many  # noqa: E402

FROZEN_GOLD = ROOT / "data" / "splits" / "held_out_gold.jsonl"
OUT = ROOT / "eval" / "held_out_diag.json"
SAMPLE_N = 2000
SEED = 7


def main() -> int:
    if not FROZEN_GOLD.exists():
        print(f"missing {FROZEN_GOLD}", file=sys.stderr)
        return 2
    gold: dict[str, str] = {}
    for line in FROZEN_GOLD.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        roman = (row.get("input") or row.get("roman") or "").lower()
        native = row.get("gold") or row.get("native")
        if not native and row.get("candidates"):
            native = row["candidates"][0].get("text")
        if roman and native:
            gold[roman] = native

    blob = ro.load_blob()
    lex = blob.get("lexicon") or {}
    eligible = [(r, n) for r, n in gold.items() if r not in lex]
    rng = random.Random(SEED)
    items = eligible
    if len(items) > SAMPLE_N:
        items = rng.sample(items, SAMPLE_N)

    missing = below6 = wrong_order = hit_top1 = 0
    samples = {"missing": [], "below6": [], "wrong_order": []}
    menus = top_six_many([roman for roman, _native in items])
    for (roman, native), texts in zip(items, menus, strict=True):
        if native not in texts:
            missing += 1
            if len(samples["missing"]) < 25:
                samples["missing"].append({"roman": roman, "gold": native, "menu": texts[:6]})
        elif native not in texts[:6]:
            below6 += 1
            if len(samples["below6"]) < 25:
                samples["below6"].append(
                    {"roman": roman, "gold": native, "rank": texts.index(native) + 1, "menu": texts[:8]}
                )
        elif texts[0] != native:
            wrong_order += 1
            if len(samples["wrong_order"]) < 25:
                samples["wrong_order"].append(
                    {"roman": roman, "gold": native, "top1": texts[0], "menu": texts[:6]}
                )
        else:
            hit_top1 += 1

    n = len(items)
    report = {
        "evaluated": n,
        "eligible_pool": len(eligible),
        "missing_from_candidates": missing,
        "generated_but_below_6": below6,
        "in_top6_wrong_order": wrong_order,
        "top1_correct": hit_top1,
        "missing_pct": round(100.0 * missing / max(1, n), 2),
        "below6_pct": round(100.0 * below6 / max(1, n), 2),
        "wrong_order_pct": round(100.0 * wrong_order / max(1, n), 2),
        "top1_pct": round(100.0 * hit_top1 / max(1, n), 2),
        "recall_at_6_pct": round(100.0 * (n - missing - below6) / max(1, n), 2),
        "samples": samples,
        "gates": {
            "recall_at_6_target_pct": 60,
            "top1_target_pct": 45,
            "top3_target_pct": 55,
            "ndcg_at_6_target": 0.5,
        },
        "note": "Frost-style: raise recall via generation/data before LTR. Soft weight floors are not equivalent across sources.",
        "ranker": "production-javascript-trie",
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "samples"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
