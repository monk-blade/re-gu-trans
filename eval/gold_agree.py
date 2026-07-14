#!/usr/bin/env python3
"""Eval frozen gold set — accepts multiple natives via `accepted` list."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
from production_rank import canonical_native, top_six_many  # noqa: E402

GOLD = ROOT / "eval" / "gold" / "gu_gold.jsonl"
OUT = ROOT / "eval" / "gold_agree_summary.json"


def main() -> int:
    rows = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    menus = top_six_many([row["roman"] for row in rows])
    ok = 0
    misses = []
    for row, texts in zip(rows, menus, strict=True):
        # Production layout guarantees Gujarati #1 and Latin echo #2.
        top = texts[0] if texts else ""
        accepted = {canonical_native(value) for value in (row.get("accepted") or [])}
        if row.get("native"):
            accepted.add(canonical_native(row["native"]))
        hit = top in accepted
        ok += int(hit)
        if not hit:
            misses.append({"roman": row["roman"], "ours": top, "gold": sorted(accepted)[:4]})
    n = len(rows)
    payload = {
        "n": n,
        "match": ok,
        "pct": round(100 * ok / n, 2) if n else 0,
        "misses": misses[:40],
        "miss_count": len(misses),
        "ranker": "production-javascript-trie",
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"gold agree: {ok}/{n} = {payload['pct']}%")
    # Smoke subset of 25 must stay 100%; full set gate soft for CI expansion
    return 0 if ok == n or (n >= 100 and payload["pct"] >= 95) else 1


if __name__ == "__main__":
    raise SystemExit(main())
