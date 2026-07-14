#!/usr/bin/env python3
"""Emit one machine-readable quality report for CI / releases."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "quality_report.json"


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str]) -> tuple[int, float]:
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return p.returncode, time.perf_counter() - t0


def main() -> int:
    # Run evals
    codes = {}
    times = {}
    for name, cmd in [
        ("smoke", [sys.executable, "eval/rank_offline.py"]),
        ("apple_integrity", [sys.executable, "eval/apple_integrity.py"]),
        ("leakage", [sys.executable, "scripts/check_lexicon_leakage.py"]),
        ("held_out", [sys.executable, "eval/held_out_agree.py"]),
        ("gold", [sys.executable, "eval/gold_agree.py"]),
        ("budgets", [sys.executable, "eval/check_budgets.py"]),
    ]:
        code, elapsed = run(cmd)
        codes[name] = code
        times[name] = round(elapsed, 3)
        if code != 0 and name == "smoke":
            print(f"{name} failed", file=sys.stderr)

    blob_path = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
    if not blob_path.exists():
        blob_path = ROOT / "rime" / "gu_lexicon_blob.json"
    blob = json.loads(blob_path.read_text(encoding="utf-8")) if blob_path.exists() else {"lexicon": {}, "weights": {}}
    lex = blob.get("lexicon") or {}
    weights = blob.get("weights") or {}
    soft = sum(1 for w in weights.values() if 0 < float(w or 0) < 100)
    strong = sum(1 for w in weights.values() if float(w or 0) >= 100)

    uni_n = 0
    uni = ROOT / "rime" / "js" / "lm" / "unigram.tsv"
    if uni.exists():
        uni_n = sum(1 for _ in uni.open())

    smoke = {}
    sr = ROOT / "eval" / "rank_results.json"
    if sr.exists():
        smoke = json.loads(sr.read_text())
    integrity = {}
    ir = ROOT / "eval" / "apple_integrity_summary.json"
    if ir.exists():
        integrity = json.loads(ir.read_text())
    held = {}
    hr = ROOT / "eval" / "held_out_agree_summary.json"
    if hr.exists():
        held = json.loads(hr.read_text())
    gold = {}
    gr = ROOT / "eval" / "gold_agree_summary.json"
    if gr.exists():
        gold = json.loads(gr.read_text())
    leak = {}
    # budgets
    budget = {}
    br = ROOT / "eval" / "budget_summary.json"
    if br.exists():
        budget = json.loads(br.read_text())

    bench = {}
    bp = ROOT / "eval" / "bench_summary.json"
    if bp.exists():
        bench = json.loads(bp.read_text())

    schema_v = "unknown"
    schema = (ROOT / "rime" / "gujarati.schema.yaml").read_text(encoding="utf-8")
    for line in schema.splitlines():
        if line.strip().startswith("version:"):
            schema_v = line.split(":", 1)[1].strip().strip("'\"")
            break

    report = {
        "schema_version": schema_v,
        "exit_codes": codes,
        "eval_seconds": times,
        "smoke": {
            "ok": smoke.get("smoke_ok"),
            "total": smoke.get("smoke_total"),
            "pass": smoke.get("smoke_ok") == smoke.get("smoke_total"),
        },
        "apple_integrity": {
            "pct": integrity.get("pct"),
            "n": integrity.get("n"),
            "disagree": (integrity.get("n") or 0) - (integrity.get("match") or 0),
        },
        "held_out": held,
        "leakage": {"pass": codes.get("leakage") == 0},
        "gold": gold,
        "assets": {
            "lexicon_total": len(lex),
            "soft": soft,
            "strong": strong,
            "unigram": uni_n,
            "hashes": {
                "lexicon_blob": sha256(blob_path),
                "lexicon_bin": sha256(ROOT / "rime" / "js" / "lexicon.trie.bin"),
                "unigram": sha256(uni),
                "stems": sha256(ROOT / "rime" / "js" / "lm" / "stems.json"),
                "attested": sha256(ROOT / "rime" / "js" / "lm" / "attested.json"),
                "schema": sha256(ROOT / "rime" / "gujarati.schema.yaml"),
                "ranking_policy": sha256(ROOT / "rime" / "js" / "ranking_policy.json"),
            },
        },
        "latency": {
            "startup_ms": bench.get("startup_ms") or budget.get("startup_ms"),
            "query_p50_ms": bench.get("query_p50_ms"),
            "query_p95_ms": bench.get("query_p95_ms") or budget.get("query_p95_ms"),
            "package_bytes": budget.get("staged_est_bytes"),
            "note": "Filled when bench/budget summaries present",
        },
        "budgets": budget,
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "smoke_pass": report["smoke"]["pass"], "integrity_pct": integrity.get("pct")}, indent=2))
    if codes.get("smoke") != 0:
        return 1
    if (integrity.get("pct") or 0) < 99.5:
        return 2
    if codes.get("leakage") not in (0, None):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
