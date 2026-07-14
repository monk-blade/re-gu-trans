#!/usr/bin/env python3
"""Leakage gate: soft∩test must be 0; report strong overlap."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOB = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
TEST = ROOT / "data" / "splits" / "test_romans.json"
OUT = ROOT / "eval" / "leakage_report.json"
STRONG = 100


def main() -> int:
    if not BLOB.exists() or not TEST.exists():
        print("missing blob or test split", file=sys.stderr)
        return 2
    blob = json.loads(BLOB.read_text(encoding="utf-8"))
    test = set(json.loads(TEST.read_text(encoding="utf-8")))
    lex = blob.get("lexicon") or {}
    weights = blob.get("weights") or {}
    soft_hit = []
    strong_hit = []
    for r in test:
        if r not in lex:
            continue
        w = float(weights.get(r, STRONG) or STRONG)
        if 0 < w < STRONG:
            soft_hit.append(r)
        else:
            strong_hit.append(r)
    payload = {
        "test_romans": len(test),
        "soft_overlap": len(soft_hit),
        "strong_overlap": len(strong_hit),
        "soft_overlap_pct": round(100 * len(soft_hit) / len(test), 2) if test else 0,
        "sample_soft": soft_hit[:20],
        "pass": len(soft_hit) == 0,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
