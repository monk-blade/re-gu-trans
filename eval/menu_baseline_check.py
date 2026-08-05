#!/usr/bin/env python3
"""Require byte-for-byte parity with the v3.1 production menu baseline."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "eval" / "fixtures" / "production_top6_v3_1.jsonl"
SOURCE = ROOT / "data" / "splits" / "held_out_gold.jsonl"
RUNNER = ROOT / "eval" / "js_production_runner.mjs"


def main() -> int:
    if not BASELINE.exists() or sum(1 for _ in BASELINE.open(encoding="utf-8")) != 2000:
        print("baseline must contain exactly 2,000 menus", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="akshar-menu-baseline-") as temp:
        actual = Path(temp) / "actual.jsonl"
        env = dict(os.environ, DEBUG_RANK="1")
        run = subprocess.run(
            ["node", str(RUNNER), "trie", str(SOURCE), str(actual), "2000"],
            cwd=ROOT,
            env=env,
            check=False,
        )
        if run.returncode:
            return run.returncode
        if BASELINE.read_bytes() != actual.read_bytes():
            print("production menu baseline changed", file=sys.stderr)
            return 1
    print("MENU_BASELINE_OK fixtures=2000 ordered_top6=100% finite=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
