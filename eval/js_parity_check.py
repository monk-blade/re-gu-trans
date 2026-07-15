#!/usr/bin/env python3
"""Gate offline/production parity by executing the production JavaScript ranker."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FIXTURES = ROOT / "data" / "splits" / "held_out_gold.jsonl"
OUT = ROOT / "eval" / "js_parity_fixtures.jsonl"
SUMMARY = ROOT / "eval" / "js_parity_summary.json"
RUNNER = ROOT / "eval" / "js_production_runner.mjs"
N = 500


def run_js(mode: str, source: Path, output: Path) -> list[dict]:
    proc = subprocess.run(
        ["node", str(RUNNER), mode, str(source), str(output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode:
        print(proc.stdout, end="")
        print(proc.stderr, end="", file=sys.stderr)
        raise SystemExit(proc.returncode)
    return [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines() if line]


def main() -> int:
    rows = []
    for line in FIXTURES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        source = json.loads(line)
        roman = (source.get("input") or source.get("roman") or "").lower()
        if not roman:
            continue
        rows.append({"roman": roman})
        if len(rows) >= N:
            break

    with OUT.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    with tempfile.TemporaryDirectory(prefix="akshar-js-parity-") as temp:
        temp_path = Path(temp)
        text_rows = run_js("text", OUT, temp_path / "text.jsonl")
        trie_rows = run_js("trie", OUT, temp_path / "trie.jsonl")

    text_by_roman = {row["roman"]: row for row in text_rows}
    trie_by_roman = {row["roman"]: row for row in trie_rows}
    binary_mismatches = []
    non_finite = []
    for expected in rows:
        roman = expected["roman"]
        text = text_by_roman.get(roman, {})
        trie = trie_by_roman.get(roman, {})
        if not text.get("finite") or not trie.get("finite"):
            non_finite.append(roman)
        if text.get("top6") != trie.get("top6"):
            binary_mismatches.append(
                {"roman": roman, "text": text.get("top6"), "trie": trie.get("top6")}
            )
    total = len(rows)
    binary_match_rate = 100.0 * (total - len(binary_mismatches)) / total if total else 0.0
    report = {
        "fixtures": total,
        "target_fixtures": N,
        "production_js_executed": True,
        "authoritative_ranker": "production-javascript",
        "offline_evaluator": "production-javascript",
        "offline_production_match_rate": round(binary_match_rate, 3),
        "binary_text_match_rate": round(binary_match_rate, 3),
        "binary_text_mismatches": len(binary_mismatches),
        "non_finite": len(non_finite),
        "binary_samples": binary_mismatches[:10],
    }
    SUMMARY.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if total != N or non_finite or binary_mismatches:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
