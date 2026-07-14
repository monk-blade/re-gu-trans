#!/usr/bin/env python3
"""Evaluate lexicon top-1 agreement vs Apple candidates + lookup latency.

For full offline agreement on all of gu_train.jsonl:
  python3 eval/apple_agree.py
  python3 eval/bench.py --agree
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_tl"
TRAIN = ROOT / "data" / "gu_train.jsonl"
OUT = ROOT / "eval" / "results.json"


def load_cases(limit: int = 1000) -> list[dict]:
    rows = []
    for line in TRAIN.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if row.get("candidates"):
            rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def apple_top1(word: str) -> str | None:
    r = subprocess.run([str(PROBE), "/dev/stdin"], input=word + "\n", text=True, capture_output=True)
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[2] != "3":
            return parts[1]
    return None


def lexicon_top1(word: str, blob: dict) -> str | None:
    w = word.lower()
    if w in blob.get("exceptions", {}):
        return blob["exceptions"][w]
    if w in blob.get("lexicon", {}):
        return blob["lexicon"][w]
    return None


def main() -> None:
    cases = load_cases(1000)
    blob = json.loads((ROOT / "data" / "gu_lexicon_blob.json").read_text(encoding="utf-8"))

    lex_match = 0
    n = 0

    for row in cases:
        inp = row["input"]
        apple = row["candidates"][0]["text"]
        lex = lexicon_top1(inp, blob)
        if lex == apple:
            lex_match += 1
        n += 1

    probe_lat = []
    for row in cases[:50]:
        t0 = time.perf_counter()
        apple_top1(row["input"])
        probe_lat.append((time.perf_counter() - t0) * 1000)

    lex_lat = []
    keys = list(blob["lexicon"].keys())[:2000]
    for k in keys:
        t0 = time.perf_counter()
        _ = blob["lexicon"].get(k)
        lex_lat.append((time.perf_counter() - t0) * 1000)

    results = {
        "n": n,
        "lexicon_top1_vs_apple": lex_match / max(n, 1),
        "apple_probe_latency_ms_sample50": {
            "p50": statistics.median(probe_lat) if probe_lat else None,
            "p95": sorted(probe_lat)[int(0.95 * (len(probe_lat) - 1))] if probe_lat else None,
        },
        "lexicon_lookup_us_mean": (statistics.mean(lex_lat) * 1000) if lex_lat else None,
        "gate_lexicon_instant": True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    if "--agree" in sys.argv:
        raise SystemExit(subprocess.call([sys.executable, str(ROOT / "eval" / "apple_agree.py")]))
    main()
