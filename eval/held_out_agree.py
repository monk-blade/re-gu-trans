#!/usr/bin/env python3
"""Clean held-out agreement: only test romans absent from runtime training sources.

Prefers committed `data/splits/held_out_gold.jsonl` (CI-safe). Optional rebuild
from `data/external/*_gu_pairs.tsv` when that cache is present locally.

Requires soft∩test leakage already purged. Reports overlap, eligible, top-1/3, MRR,
recall@6, NDCG@6.
"""
from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import rank_offline as ro  # noqa: E402

EXT = ROOT / "data" / "external"
SPLITS = ROOT / "data" / "splits" / "test_romans.json"
FROZEN_GOLD = ROOT / "data" / "splits" / "held_out_gold.jsonl"
OUT = ROOT / "eval" / "held_out_agree_summary.json"
SAMPLE_N = 2000
SEED = 7
STRONG = 100
MIN_ELIGIBLE = 1000


def ndcg_at_k(ranked: list[str], gold: str, k: int = 6) -> float:
    if gold not in ranked[:k]:
        return 0.0
    idx = ranked.index(gold)
    return 1.0 / math.log2(idx + 2)


def load_gold(test: set[str]) -> tuple[dict[str, str], str]:
    """Return (roman→native, source_note). Prefer frozen CI gold."""
    gold: dict[str, str] = {}
    if FROZEN_GOLD.exists():
        for line in FROZEN_GOLD.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            r = str(row["roman"]).lower()
            if r in test:
                gold[r] = row["native"]
        return gold, str(FROZEN_GOLD.relative_to(ROOT))

    for path in (EXT / "aksharantar_gu_pairs.tsv", EXT / "dakshina_gu_pairs.tsv"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            r, n = parts[0].lower(), parts[1]
            if r in test and r not in gold:
                gold[r] = n
    if gold:
        return gold, "data/external/*_gu_pairs.tsv"
    return {}, "missing"


def main() -> int:
    if not SPLITS.exists():
        print("missing splits — run scripts/build_eval_splits.py", file=sys.stderr)
        return 2
    test = set(json.loads(SPLITS.read_text(encoding="utf-8")))
    gold, gold_src = load_gold(test)
    if not gold:
        print(
            "FAIL: no held-out gold — commit data/splits/held_out_gold.jsonl "
            "(scripts/build_held_out_gold.py)",
            file=sys.stderr,
        )
        return 2

    blob = ro.load_blob()
    lex = blob.get("lexicon") or {}
    weights = blob.get("weights") or {}
    soft_overlap = strong_overlap = 0
    for r in test:
        if r not in lex:
            continue
        w = float(weights.get(r, STRONG) or STRONG)
        if 0 < w < STRONG:
            soft_overlap += 1
        else:
            strong_overlap += 1

    # Eligible: in gold ∩ test and NOT in runtime lexicon at all
    eligible = [(r, n) for r, n in gold.items() if r not in lex]
    if soft_overlap:
        print(f"FAIL: soft∩test leakage={soft_overlap} — run purge_soft_test_leakage.py", file=sys.stderr)
        payload = {
            "report": "held_out_agree",
            "clean": False,
            "soft_overlap": soft_overlap,
            "strong_overlap": strong_overlap,
            "eligible": len(eligible),
            "gold_source": gold_src,
        }
        OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 1

    uni = ro.load_unigram()
    stems = ro.load_stems()
    attested, floor = ro.load_attested()
    pfx = ro.build_prefix_index(lex)
    rng = random.Random(SEED)
    items = eligible
    if len(items) > SAMPLE_N:
        items = rng.sample(items, SAMPLE_N)

    ok = top3 = recall6 = 0
    rr = ndcg = 0.0
    in_lex_eval = 0
    for roman, native in items:
        if roman in lex:
            in_lex_eval += 1
            continue
        ranked = ro.rank(roman, blob, uni, stems, attested, floor, pfx)
        texts = [t for t, _a, _b in ranked]
        if texts and texts[0] == native:
            ok += 1
            top3 += 1
            recall6 += 1
            rr += 1.0
        else:
            if native in texts[:3]:
                top3 += 1
            if native in texts[:6]:
                recall6 += 1
            if native in texts:
                rr += 1.0 / (texts.index(native) + 1)
        ndcg += ndcg_at_k(texts, native, 6)

    n = len(items) - in_lex_eval
    payload = {
        "report": "held_out_agree",
        "clean": True,
        "note": "Eligible = test∩source gold with roman absent from runtime lexicon",
        "gold_source": gold_src,
        "test_romans": len(test),
        "soft_overlap": soft_overlap,
        "strong_overlap": strong_overlap,
        "eligible_pool": len(eligible),
        "evaluated": n,
        "evaluated_in_lex_skipped": in_lex_eval,
        "top1": ok,
        "top1_pct": round(100 * ok / n, 2) if n else 0,
        "top3": top3,
        "top3_pct": round(100 * top3 / n, 2) if n else 0,
        "recall_at_6": recall6,
        "recall_at_6_pct": round(100 * recall6 / n, 2) if n else 0,
        "mrr": round(rr / n, 4) if n else 0,
        "ndcg_at_6": round(ndcg / n, 4) if n else 0,
        "baseline_invalid_prior_pct": 46.87,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if n < MIN_ELIGIBLE:
        print(f"FAIL: eligible evaluated {n} < {MIN_ELIGIBLE}", file=sys.stderr)
        return 2
    if in_lex_eval:
        print(f"FAIL: {in_lex_eval} evaluated items still in runtime lex", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
