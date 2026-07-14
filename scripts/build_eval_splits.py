#!/usr/bin/env python3
"""Deterministic source-stratified train/dev/test roman splits (leakage control).

Hash(roman + seed) → bucket. Soft ingest / trie build must exclude test romans.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "external"
OUT = ROOT / "data" / "splits"
SEED = "re-gu-trans-splits-v1"
# 80/10/10
TRAIN_MAX = 0.80
DEV_MAX = 0.90


def bucket(roman: str) -> str:
    h = hashlib.sha256((SEED + "\0" + roman.lower()).encode()).hexdigest()
    x = int(h[:8], 16) / 0xFFFFFFFF
    if x < TRAIN_MAX:
        return "train"
    if x < DEV_MAX:
        return "dev"
    return "test"


def load_romans(*paths: Path) -> dict[str, set[str]]:
    by_src: dict[str, set[str]] = defaultdict(set)
    for path in paths:
        if not path.exists():
            continue
        src = path.stem
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            roman = parts[0].strip().lower()
            if 2 <= len(roman) <= 32:
                by_src[src].add(roman)
    return by_src


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    by_src = load_romans(
        EXT / "aksharantar_gu_pairs.tsv",
        EXT / "dakshina_gu_pairs.tsv",
    )
    all_romans = sorted({r for s in by_src.values() for r in s})
    splits = {"train": [], "dev": [], "test": []}
    for r in all_romans:
        splits[bucket(r)].append(r)

    meta = {
        "seed": SEED,
        "counts": {k: len(v) for k, v in splits.items()},
        "sources": {k: len(v) for k, v in by_src.items()},
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    for name, romans in splits.items():
        (OUT / f"{name}_romans.txt").write_text("\n".join(romans) + "\n", encoding="utf-8")
    # Convenience JSON set for ingest
    (OUT / "test_romans.json").write_text(
        json.dumps(splits["test"], ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
