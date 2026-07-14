#!/usr/bin/env python3
"""Training-source soft-pair top-1 report (leaky until P2 holds out test keys).

Samples Aksharantar/Dakshina pairs whose romans are not strong (≥100) keys.
Many soft keys are already in the lexicon — treat as training-source integrity,
not true OOV generalization.

Writes: eval/training_source_agree_summary.json (+ soft_oov_agree_summary.json alias)
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import rank_offline as ro  # noqa: E402

EXT = ROOT / "data" / "external"
AKSHA = EXT / "aksharantar_gu_pairs.tsv"
DAK = EXT / "dakshina_gu_pairs.tsv"
SUMMARY = ROOT / "eval" / "training_source_agree_summary.json"
LEGACY = ROOT / "eval" / "soft_oov_agree_summary.json"
LEXICON_STRONG = 100
SAMPLE_N = 2000
SEED = 42


def load_pairs(path: Path) -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        roman, native = parts[0].lower(), parts[1]
        cnt = int(parts[2]) if len(parts) >= 3 and parts[2].strip().lstrip("-").isdigit() else 1
        if 3 <= len(roman) <= 14:
            out.append((roman, native, cnt))
    return out


def main() -> int:
    blob = ro.load_blob()
    lex = blob.get("lexicon") or {}
    weights = blob.get("weights") or {}
    uni = ro.load_unigram()
    stems = ro.load_stems()
    attested, floor = ro.load_attested()
    prefix_index = ro.build_prefix_index(lex)
    strong = {k for k, w in weights.items() if float(w or 0) >= LEXICON_STRONG}

    pool: list[tuple[str, str, str]] = []
    for roman, native, _ in load_pairs(AKSHA):
        if roman not in strong:
            pool.append((roman, native, "aksharantar"))
    for roman, native, _ in load_pairs(DAK):
        if roman not in strong:
            pool.append((roman, native, "dakshina"))

    rng = random.Random(SEED)
    sample = rng.sample(pool, SAMPLE_N) if len(pool) > SAMPLE_N else pool
    ok = 0
    by_src = {"aksharantar": [0, 0], "dakshina": [0, 0]}
    by_len = {"3-6": [0, 0], "7-10": [0, 0], "11+": [0, 0]}
    misses = []
    for roman, native, src in sample:
        ranked = ro.rank(roman, blob, uni, stems, attested, floor, prefix_index)
        top = ranked[0][0] if ranked else ""
        hit = top == native
        ok += int(hit)
        by_src[src][1] += 1
        by_src[src][0] += int(hit)
        lb = "3-6" if len(roman) <= 6 else ("7-10" if len(roman) <= 10 else "11+")
        by_len[lb][1] += 1
        by_len[lb][0] += int(hit)
        if not hit and len(misses) < 20:
            misses.append({"roman": roman, "ours": top, "gold": native, "src": src})

    n = len(sample)
    pct = round(100.0 * ok / n, 2) if n else 0.0
    payload = {
        "report": "training_source_agree",
        "note": "Training-source / soft-lex in-sample until leakage-free splits",
        "n": n,
        "match": ok,
        "pct": pct,
        "by_source": {
            k: {"ok": v[0], "n": v[1], "pct": round(100 * v[0] / v[1], 2) if v[1] else 0}
            for k, v in by_src.items()
        },
        "by_length": {
            k: {"ok": v[0], "n": v[1], "pct": round(100 * v[0] / v[1], 2) if v[1] else 0}
            for k, v in by_len.items()
        },
        "sample_misses": misses,
    }
    SUMMARY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    LEGACY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"training-source agree: {ok}/{n} = {pct}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
