#!/usr/bin/env python3
"""Require ordered production menu parity between binary-shaped and text storage."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
OUT = ROOT / "eval" / "binary_text_parity_summary.json"
JS_SUMMARY = ROOT / "eval" / "js_parity_summary.json"


def parse_native_lm_payload(raw: str) -> dict:
    if raw is None or raw == "":
        return {"unigram": 0, "stem": 0, "attested": False}
    s = str(raw)
    parts = s.split("\t") if "\t" in s else s.split("\x1f")
    return {
        "unigram": int(parts[0]) if parts and str(parts[0]).isdigit() else int(float(parts[0] or 0)),
        "stem": int(parts[1]) if len(parts) > 1 and str(parts[1]).isdigit() else int(float(parts[1] or 0) if len(parts) > 1 else 0),
        "attested": (parts[2] if len(parts) > 2 else "0") in ("1", "true", True, 1),
    }


def main() -> int:
    # Payload format from build_qjs_tries
    sample = parse_native_lm_payload("42\t7\t1")
    assert sample == {"unigram": 42, "stem": 7, "attested": True}

    nat_tsv = ROOT / "rime" / "js" / "native_lm.tsv"
    checked = 0
    mismatches = 0
    if nat_tsv.exists():
        for i, line in enumerate(nat_tsv.read_text(encoding="utf-8").splitlines()):
            if i >= 200:
                break
            if not line or "\t" not in line:
                continue
            native, payload = line.split("\t", 1)
            parsed = parse_native_lm_payload(payload)
            # Round-trip encode
            again = parse_native_lm_payload(f"{parsed['unigram']}\t{parsed['stem']}\t{1 if parsed['attested'] else 0}")
            if again != parsed:
                mismatches += 1
            checked += 1

    process = subprocess.run(
        [sys.executable, "eval/js_parity_check.py"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode:
        print(process.stdout, end="")
        print(process.stderr, end="", file=sys.stderr)
        return process.returncode
    parity = json.loads(JS_SUMMARY.read_text(encoding="utf-8"))

    report = {
        "native_lm_lines_checked": checked,
        "payload_mismatches": mismatches,
        "production_js_executed": parity.get("production_js_executed"),
        "fixtures": parity.get("fixtures"),
        "ordered_top6_match_rate": parity.get("binary_text_match_rate"),
        "ordered_top6_mismatches": parity.get("binary_text_mismatches"),
        "non_finite": parity.get("non_finite"),
        "note": "Production engine.js executed with text and Trie-shaped storage",
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    if mismatches:
        return 1
    if not report["production_js_executed"]:
        return 2
    if report["fixtures"] != 500 or report["ordered_top6_match_rate"] != 100.0:
        return 3
    if report["ordered_top6_mismatches"] or report["non_finite"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
