#!/usr/bin/env python3
"""Stratified production-JS quality and large deterministic stress report."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

from production_rank import rank_many, top_six_many

ROOT = Path(__file__).resolve().parents[1]
HELD_OUT = ROOT / "data" / "splits" / "held_out_gold.jsonl"
SOURCE_DISJOINT = ROOT / "data" / "splits" / "apple_class_source_disjoint.jsonl"
SHORT_BEHAVIOR = ROOT / "data" / "splits" / "apple_class_short_behavior.jsonl"
OUT = ROOT / "eval" / "apple_class_quality_summary.json"


def length_band(roman: str) -> str:
    n = len(roman)
    return "1-3" if n <= 3 else "4-6" if n <= 6 else "7-9" if n <= 9 else "10-14" if n <= 14 else "15+"


def accuracy(rows: list[dict], menus: list[list[str]]) -> dict:
    by_band: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    total = [0, 0, 0, 0]
    for row, menu in zip(rows, menus, strict=True):
        values = [1, int(bool(menu) and menu[0] == row["native"]), int(row["native"] in menu[:3]), int(row["native"] in menu[:6])]
        band = by_band[length_band(row["roman"])]
        for index, value in enumerate(values):
            band[index] += value
            total[index] += value
    def format_values(values: list[int]) -> dict:
        n, top1, top3, recall6 = values
        return {"n": n, "top1_pct": round(100 * top1 / n, 2) if n else None, "top3_pct": round(100 * top3 / n, 2) if n else None, "recall_at_6_pct": round(100 * recall6 / n, 2) if n else None}
    return {"overall": format_values(total), "by_length": {key: format_values(by_band[key]) for key in ("1-3", "4-6", "7-9", "10-14", "15+")}}


def stress_romans(limit: int) -> list[str]:
    blob_path = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
    blob = json.loads(blob_path.read_text(encoding="utf-8"))
    keys = sorted((blob.get("lexicon") or {}).keys())
    out: list[str] = []
    seen: set[str] = set()
    transforms = (
        lambda key: key,
        lambda key: key + "a",
        lambda key: key.replace("v", "w", 1) if "v" in key else key + "i",
    )
    for transform in transforms:
        for key in keys:
            roman = transform(key)
            if not roman or roman in seen:
                continue
            seen.add(roman)
            out.append(roman)
            if len(out) >= limit:
                return out
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stress", type=int, default=10_000, help="production queries; use 250000 for the full gate")
    parser.add_argument("--chunk", type=int, default=25_000)
    parser.add_argument("--require-full", action="store_true")
    parser.add_argument("--enforce-targets", action="store_true")
    args = parser.parse_args()

    held = [json.loads(line) for line in HELD_OUT.read_text(encoding="utf-8").splitlines() if line]
    held_menus = top_six_many([row["roman"] for row in held])
    quality = accuracy(held, held_menus)
    source_rows = [json.loads(line) for line in SOURCE_DISJOINT.read_text(encoding="utf-8").splitlines() if line] if SOURCE_DISJOINT.exists() else []
    source_quality = accuracy(source_rows, top_six_many([row["roman"] for row in source_rows])) if source_rows else None
    short_rows = [json.loads(line) for line in SHORT_BEHAVIOR.read_text(encoding="utf-8").splitlines() if line] if SHORT_BEHAVIOR.exists() else []
    short_menus = top_six_many([row["roman"] for row in short_rows]) if short_rows else []
    short_top1 = sum(bool(menu) and menu[0] in row["acceptable"] for row, menu in zip(short_rows, short_menus, strict=True))

    romans = stress_romans(max(1, args.stress))
    digest = hashlib.sha256()
    started = time.perf_counter()
    finite = True
    count = 0
    first_results: list[list[str]] = []
    for offset in range(0, len(romans), max(1, args.chunk)):
        rows = rank_many(romans[offset:offset + args.chunk])
        for row in rows:
            finite = finite and bool(row.get("finite"))
            menu = [str(item) for item in row.get("top6", [])]
            digest.update(json.dumps(menu, ensure_ascii=False, separators=(",", ":")).encode())
            if count < 1_000:
                first_results.append(menu)
            count += 1
    elapsed = time.perf_counter() - started
    repeat = top_six_many(romans[:1_000])
    deterministic = repeat == first_results

    core_targets = {
        "top1_pct": quality["overall"]["top1_pct"] >= 45,
        "top3_pct": quality["overall"]["top3_pct"] >= 55,
        "recall_at_6_pct": quality["overall"]["recall_at_6_pct"] >= 60,
        "short_behavior_top1_pct": (round(100 * short_top1 / len(short_rows), 2) if short_rows else 0) >= 80,
        "length_10_14_recall_at_6_pct": (quality["by_length"]["10-14"]["recall_at_6_pct"] or 0) >= 55,
        "length_15_plus_recall_at_6_pct": (quality["by_length"]["15+"]["recall_at_6_pct"] or 0) >= 45,
    }
    payload = {
        "report": "apple_class_quality",
        "held_out": quality,
        "source_disjoint": source_quality,
        "short_behavior": {
            "n": len(short_rows),
            "top1_pct": round(100 * short_top1 / len(short_rows), 2) if short_rows else None,
        },
        "stress": {
            "requested": args.stress,
            "executed": count,
            "finite": finite,
            "deterministic_first_1000": deterministic,
            "seconds": round(elapsed, 3),
            "queries_per_second": round(count / elapsed, 1) if elapsed else None,
            "ordered_menu_sha256": digest.hexdigest(),
            "full_gate": count >= 250_000,
        },
        "core_targets": {"checks": core_targets, "passed": all(core_targets.values())},
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not finite or not deterministic:
        return 1
    if args.require_full and count < 250_000:
        return 2
    if args.enforce_targets and not all(core_targets.values()):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
