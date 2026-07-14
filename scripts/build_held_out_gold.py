#!/usr/bin/env python3
"""Rebuild data/splits/held_out_gold.jsonl from local external pair caches.

CI commits the frozen sample so held_out_agree.py does not need data/external/.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "external"
SPLITS = ROOT / "data" / "splits" / "test_romans.json"
BLOB = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
OUT = ROOT / "data" / "splits" / "held_out_gold.jsonl"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", type=int, default=2500, help="Frozen sample size")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if not SPLITS.exists():
        print("missing test_romans.json", file=sys.stderr)
        return 2
    test = set(json.loads(SPLITS.read_text(encoding="utf-8")))
    lex = (json.loads(BLOB.read_text(encoding="utf-8")).get("lexicon") or {}) if BLOB.exists() else {}

    gold: dict[str, str] = {}
    for path in (EXT / "aksharantar_gu_pairs.tsv", EXT / "dakshina_gu_pairs.tsv"):
        if not path.exists():
            print(f"skip missing {path}", file=sys.stderr)
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            r, n = parts[0].lower(), parts[1]
            if r in test and r not in gold and r not in lex:
                gold[r] = n

    if len(gold) < 1000:
        print(f"FAIL: only {len(gold)} eligible — need external pair caches", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    items = list(gold.items())
    if len(items) > args.keep:
        items = rng.sample(items, args.keep)
    items.sort(key=lambda x: x[0])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for r, n in items:
            f.write(json.dumps({"roman": r, "native": n}, ensure_ascii=False) + "\n")
    print(f"wrote {OUT} eligible_pool={len(gold)} frozen={len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
