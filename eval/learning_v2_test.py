#!/usr/bin/env python3
"""Run the production QuickJS learning/selection contract tests."""
from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QJS = ROOT / "vendor" / "librime-qjs" / "qjs"
OUT = ROOT / "eval" / "learning_v2_summary.json"


def main() -> int:
    command = (
        [str(QJS), "-m", "eval/learning_v2_test.js"]
        if platform.system() == "Darwin"
        else ["node", "eval/learning_v2_test.js"]
    )
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        print(proc.stdout, end="")
        print(proc.stderr, end="")
        return proc.returncode
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    if not lines:
        raise SystemExit("production JavaScript learning test produced no JSON result")
    report = json.loads(lines[-1])
    if not report.get("ok") or not report.get("production_js"):
        raise SystemExit("production JavaScript learning contract failed")
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
