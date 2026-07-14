#!/usr/bin/env python3
"""Held-out soft OOV top-1 vs Aksharantar / Dakshina pairs (not Apple train).

Samples roman→native pairs absent from strong lexicon (weight ≥100), ranks with
eval.rank_offline, reports top-1 rate. Gates soft-cap growth alongside apple_agree.

Writes: eval/soft_oov_agree_summary.json
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
SUMMARY = ROOT / "eval" / "soft_oov_agree_summary.json"
LEXICON_STRONG = 100
SAMPLE_N = 2000
SEED = 42


def load_pairs(path: Path, limit: int | None = None) -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        roman, native = parts[0].lower(), parts[1]
        cnt = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 1
        if len(roman) < 3 or len(roman) > 14:
            continue
        out.append((roman, native, cnt))
        if limit and len(out) >= limit:
            break
    return out


def main() -> int:
    blob = ro.load_blob()
    lex = blob.get("lexicon") or {}
    weights = blob.get("weights") or {}
    uni = ro.load_unigram()
    stems = ro.load_stems()
    attested, floor = ro.load_attested()
    prefix_index = ro.build_prefix_index(lex)

    # Strong keys = never soft OOV eval
    strong = {k for k, w in weights.items() if float(w or 0) >= LEXICON_STRONG}

    pool: list[tuple[str, str, str]] = []  # roman, native, source
    for roman, native, _cnt in load_pairs(AKSHA):
        if roman in strong:
            continue
        pool.append((roman, native, "aksharantar"))
    for roman, native, _cnt in load_pairs(DAK):
        if roman in strong:
            continue
        pool.append((roman, native, "dakshina"))

    rng = random.Random(SEED)
    if len(pool) > SAMPLE_N:
        sample = rng.sample(pool, SAMPLE_N)
    else:
        sample = pool

    ok = 0
    by_src: dict[str, list[int]] = {"aksharantar": [0, 0], "dakshina": [0, 0]}
    by_len: dict[str, list[int]] = {"3-6": [0, 0], "7-10": [0, 0], "11+": [0, 0]}
    misses: list[dict] = []

    for roman, native, src in sample:
        ranked = ro.rank(roman, blob, uni, stems, attested, floor, prefix_index)
        top = ranked[0][0] if ranked else None
        hit = top == native
        ok += int(hit)
        by_src[src][1] += 1
        by_src[src][0] += int(hit)
        if len(roman) <= 6:
            bucket = "3-6"
        elif len(roman) <= 10:
            bucket = "7-10"
        else:
            bucket = "11+"
        by_len[bucket][1] += 1
        by_len[bucket][0] += int(hit)
        if not hit and len(misses) < 40:
            misses.append({"roman": roman, "expect": native, "top1": top, "src": src})

    n = len(sample)
    pct = (ok / n) if n else 0.0
    summary = {
        "n": n,
        "match": ok,
        "pct": round(pct * 100, 2),
        "by_source": {
            s: {"ok": a, "n": b, "pct": round(100 * a / b, 2) if b else 0.0}
            for s, (a, b) in by_src.items()
        },
        "by_length": {
            s: {"ok": a, "n": b, "pct": round(100 * a / b, 2) if b else 0.0}
            for s, (a, b) in by_len.items()
        },
        "sample_misses": misses,
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"soft OOV agree: {ok}/{n} = {pct:.2%}")
    for s, st in summary["by_source"].items():
        print(f"  {s}: {st['ok']}/{st['n']} ({st['pct']}%)")
    for s, st in summary["by_length"].items():
        print(f"  len {s}: {st['ok']}/{st['n']} ({st['pct']}%)")
    print(f"wrote {SUMMARY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
