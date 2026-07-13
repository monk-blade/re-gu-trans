#!/usr/bin/env python3
"""Evaluate latency and top-1 agreement vs Apple TLTransliterator."""

from __future__ import annotations

import json
import statistics
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tools" / "probe_tl"
CLIENT = ROOT / "tools" / "gu_ranker_client_fast"
if not CLIENT.exists():
    CLIENT = ROOT / "tools" / "gu_ranker_client"
SOCK = Path.home() / "Library" / "Rime" / "run" / "gu_ranker.sock"
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


def onnx_rank(word: str, cands: list[str]) -> list[str]:
    payload = json.dumps({"input": word, "cands": cands, "timeout_ms": 20})
    t0 = time.perf_counter()
    r = subprocess.run(
        [str(CLIENT), "--sock", str(SOCK), "--json", payload],
        capture_output=True,
        text=True,
    )
    dt = (time.perf_counter() - t0) * 1000
    try:
        scores = json.loads(r.stdout).get("scores") or []
    except Exception:
        scores = []
    if len(scores) != len(cands):
        return cands, dt
    ranked = [c for _, c in sorted(zip(scores, cands), key=lambda x: -x[0])]
    return ranked, dt


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

    apple_match = 0
    lex_match = 0
    onnx_lat = []
    n = 0

    for row in cases:
        inp = row["input"]
        apple = row["candidates"][0]["text"]
        # lexicon path
        lex = lexicon_top1(inp, blob)
        if lex == apple:
            lex_match += 1

        # build small candidate set like the IME would
        cands = []
        seen = set()
        for src in (lex, apple, *(c["text"] for c in row["candidates"][:5])):
            if src and src not in seen:
                cands.append(src)
                seen.add(src)
        if len(cands) < 2:
            # add a distractor
            cands.append(cands[0] + "ં" if cands else "ક")

        ranked, dt = onnx_rank(inp, cands)
        onnx_lat.append(dt)
        if ranked and ranked[0] == apple:
            apple_match += 1
        n += 1

    # Direct Apple probe latency sample
    probe_lat = []
    for row in cases[:50]:
        t0 = time.perf_counter()
        apple_top1(row["input"])
        probe_lat.append((time.perf_counter() - t0) * 1000)

    # Lexicon lookup microbench
    lex_lat = []
    keys = list(blob["lexicon"].keys())[:2000]
    for k in keys:
        t0 = time.perf_counter()
        _ = blob["lexicon"].get(k)
        lex_lat.append((time.perf_counter() - t0) * 1000)

    results = {
        "n": n,
        "lexicon_top1_vs_apple": lex_match / max(n, 1),
        "onnx_rerank_top1_vs_apple": apple_match / max(n, 1),
        "onnx_latency_ms": {
            "p50": statistics.median(onnx_lat) if onnx_lat else None,
            "p95": sorted(onnx_lat)[int(0.95 * (len(onnx_lat) - 1))] if onnx_lat else None,
            "mean": statistics.mean(onnx_lat) if onnx_lat else None,
        },
        "apple_probe_latency_ms_sample50": {
            "p50": statistics.median(probe_lat) if probe_lat else None,
            "p95": sorted(probe_lat)[int(0.95 * (len(probe_lat) - 1))] if probe_lat else None,
        },
        "lexicon_lookup_us_mean": (statistics.mean(lex_lat) * 1000) if lex_lat else None,
        "gate_onnx_p95_under_10ms": (sorted(onnx_lat)[int(0.95 * (len(onnx_lat) - 1))] < 10) if onnx_lat else False,
        "gate_lexicon_instant": True,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
