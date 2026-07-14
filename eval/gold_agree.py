#!/usr/bin/env python3
"""Eval frozen gold set — accepts multiple natives via `accepted` list."""
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
        # Skip latin echo at slot 2 when scoring gold natives
        texts = [t for t, tier, _ in ranked if tier != ro.TIER_LATIN]
        top = texts[0] if texts else ""
        accepted = set(row.get("accepted") or [])
        if row.get("native"):
            accepted.add(row["native"])
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
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"gold agree: {ok}/{n} = {payload['pct']}%")
    # Smoke subset of 25 must stay 100%; full set gate soft for CI expansion
    return 0 if ok == n or (n >= 100 and payload["pct"] >= 95) else 1


if __name__ == "__main__":
    raise SystemExit(main())
