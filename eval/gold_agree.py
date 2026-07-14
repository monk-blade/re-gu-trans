#!/usr/bin/env python3
"""Eval frozen gold set (never used as exception lists)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import rank_offline as ro  # noqa: E402

GOLD = ROOT / "eval" / "gold" / "gu_gold.jsonl"
OUT = ROOT / "eval" / "gold_agree_summary.json"


def main() -> int:
    rows = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    blob = ro.load_blob()
    uni = ro.load_unigram()
    stems = ro.load_stems()
    attested, floor = ro.load_attested()
    pfx = ro.build_prefix_index(blob.get("lexicon") or {})
    ok = 0
    misses = []
    for row in rows:
        ranked = ro.rank(row["roman"], blob, uni, stems, attested, floor, pfx)
        top = ranked[0][0] if ranked else ""
        hit = top == row["native"]
        ok += int(hit)
        if not hit:
            misses.append({"roman": row["roman"], "ours": top, "gold": row["native"]})
    n = len(rows)
    payload = {"n": n, "match": ok, "pct": round(100 * ok / n, 2) if n else 0, "misses": misses}
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"gold agree: {ok}/{n} = {payload['pct']}%")
    return 0 if ok == n else 1


if __name__ == "__main__":
    raise SystemExit(main())
