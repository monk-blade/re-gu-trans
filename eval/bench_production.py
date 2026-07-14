#!/usr/bin/env python3
"""Measure production JavaScript ranking latency over frozen fixtures."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "eval" / "js_parity_fixtures.jsonl"
OUT = ROOT / "eval" / "bench_summary.json"


def main() -> int:
    if not FIXTURES.exists():
        process = subprocess.run([sys.executable, "eval/js_parity_check.py"], cwd=ROOT)
        if process.returncode:
            return process.returncode
    with tempfile.TemporaryDirectory(prefix="akshar-bench-") as temp:
        output = Path(temp) / "menus.jsonl"
        process = subprocess.run(
            ["node", "eval/js_production_runner.mjs", "trie", str(FIXTURES), str(output)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    if process.returncode:
        print(process.stdout, end="")
        print(process.stderr, end="", file=sys.stderr)
        return process.returncode
    lines = [line for line in process.stdout.splitlines() if line.startswith("{")]
    if not lines:
        print("FAIL: production benchmark returned no timing JSON", file=sys.stderr)
        return 2
    report = json.loads(lines[-1])
    report.update(
        {
            "ranker": "production-javascript-trie",
            "host_storage": "file-backed-trie-emulation",
            "startup_heap_gate": "requires real librime host",
            "query_p95_budget_ms": 5,
            "query_p95_ok": report.get("query_p95_ms") is not None
            and report["query_p95_ms"] <= 5,
        }
    )
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["finite"] and report["cases"] >= 500 and report["query_p95_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
