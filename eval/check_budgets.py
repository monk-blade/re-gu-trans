#!/usr/bin/env python3
"""CI budget harness: package size, (optional) latency placeholders.

Enforces: staged data ≤70MB; beam≤64 in ranking_policy.json.
Startup/heap/query budgets recorded when eval/bench_summary.json present.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "budget_summary.json"
MAX_STAGE_BYTES = 70 * 1024 * 1024
MAX_BEAM = 64


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def main() -> int:
    policy = json.loads((ROOT / "rime" / "js" / "ranking_policy.json").read_text())
    beam = int((policy.get("lattice") or {}).get("beam") or 0)
    js = ROOT / "rime" / "js"
    bins = list(js.glob("*.trie.bin")) + list(js.glob("native_lm.trie.bin"))
    bin_bytes = sum(p.stat().st_size for p in bins if p.exists())
    # Approximate staged data = bins + small JSON (not full blob)
    small = [
        js / "exceptions.json",
        js / "emoji_keywords.json",
        js / "ranking_policy.json",
        js / "ltr_coefficients.json",
        ROOT / "rime" / "gujarati.schema.yaml",
    ]
    small_bytes = sum(p.stat().st_size for p in small if p.exists())
    js_modules = sum(
        p.stat().st_size
        for p in js.glob("*.js")
        if p.is_file()
    )
    staged_est = bin_bytes + small_bytes + js_modules

    bench = {}
    bp = ROOT / "eval" / "bench_summary.json"
    if bp.exists():
        bench = json.loads(bp.read_text())

    report = {
        "beam": beam,
        "beam_ok": beam <= MAX_BEAM,
        "bin_bytes": bin_bytes,
        "staged_est_bytes": staged_est,
        "staged_ok": staged_est <= MAX_STAGE_BYTES,
        "startup_ms": bench.get("startup_ms"),
        "heap_mb": bench.get("heap_mb"),
        "query_p95_ms": bench.get("query_p95_ms"),
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
    if bench.get("startup_ms") is not None and bench["startup_ms"] > 1000:
        return 3
    if bench.get("query_p95_ms") is not None and bench["query_p95_ms"] > 5:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
