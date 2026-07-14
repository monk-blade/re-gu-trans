#!/usr/bin/env python3
"""CI budget harness — package size, beam, and optional runtime benches.

Env:
  REQUIRE_BENCH=1 — fail if startup/heap/query metrics are null or over budget.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "budget_summary.json"
MAX_STAGE_BYTES = 70 * 1024 * 1024
MAX_BEAM = 64


def main() -> int:
    require_bench = os.environ.get("REQUIRE_BENCH", "0") == "1"
    policy = json.loads((ROOT / "rime" / "js" / "ranking_policy.json").read_text())
    beam = int((policy.get("lattice") or {}).get("beam") or 0)
    js = ROOT / "rime" / "js"
    bins = [js / "lexicon.trie.bin", js / "prefix.trie.bin", js / "native_lm.trie.bin"]
    bin_bytes = sum(p.stat().st_size for p in bins if p.exists())
    small = [
        js / "exceptions.json",
        js / "emoji_keywords.json",
        js / "ranking_policy.json",
        js / "ltr_coefficients.json",
        ROOT / "rime" / "gujarati.schema.yaml",
    ]
    small_bytes = sum(p.stat().st_size for p in small if p.exists())
    js_modules = sum(p.stat().st_size for p in js.glob("*.js") if p.is_file())
    staged_est = bin_bytes + small_bytes + js_modules

    bench = {}
    bp = ROOT / "eval" / "bench_summary.json"
    if bp.exists():
        bench = json.loads(bp.read_text(encoding="utf-8"))

    report = {
        "beam": beam,
        "beam_ok": beam <= MAX_BEAM,
        "bin_bytes": bin_bytes,
        "staged_est_bytes": staged_est,
        "staged_ok": staged_est <= MAX_STAGE_BYTES,
        "startup_ms": bench.get("startup_ms"),
        "heap_mb": bench.get("heap_mb"),
        "query_p95_ms": bench.get("query_p95_ms"),
        "require_bench": require_bench,
        "budgets": {
            "startup_ms": 1000,
            "heap_mb": 150,
            "query_p95_ms": 5,
            "staged_mb": 70,
            "beam": 64,
        },
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

    if beam > MAX_BEAM:
        print("FAIL: beam > 64", file=sys.stderr)
        return 1
    if staged_est > MAX_STAGE_BYTES:
        print(f"FAIL: staged estimate {staged_est} > {MAX_STAGE_BYTES}", file=sys.stderr)
        return 2

    startup = bench.get("startup_ms")
    heap = bench.get("heap_mb")
    p95 = bench.get("query_p95_ms")
    if require_bench:
        if startup is None or heap is None or p95 is None:
            print("FAIL: REQUIRE_BENCH=1 but bench metrics are null", file=sys.stderr)
            return 5
        if startup > 1000:
            return 3
        if heap > 150:
            print("FAIL: heap_mb > 150", file=sys.stderr)
            return 6
        if p95 > 5:
            return 4
    else:
        # Node's file-backed Trie fixture parses generated text sources at
        # startup and is not representative of librime binary loading. Gate
        # startup/heap only in the real-host benchmark job.
        if p95 is not None and p95 > 5:
            return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
