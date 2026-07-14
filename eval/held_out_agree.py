#!/usr/bin/env python3
"""True held-out top-1 on test-split romans (exclude from soft lex when rebuilt).

Uses data/splits/test_romans.json ∩ Aksharantar/Dakshina gold natives.
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
SPLITS = ROOT / "data" / "splits" / "test_romans.json"
OUT = ROOT / "eval" / "held_out_agree_summary.json"
SAMPLE_N = 1500
SEED = 7


def main() -> int:
    if not SPLITS.exists():
        print("missing splits — run scripts/build_eval_splits.py", file=sys.stderr)
        return 2
    test = set(json.loads(SPLITS.read_text(encoding="utf-8")))
    # Build roman→native from sources for test keys only
    gold: dict[str, str] = {}
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
    blob = ro.load_blob()
    uni = ro.load_unigram()
    stems = ro.load_stems()
    attested, floor = ro.load_attested()
    pfx = ro.build_prefix_index(blob.get("lexicon") or {})
    items = list(gold.items())
    rng = random.Random(SEED)
    if len(items) > SAMPLE_N:
        items = rng.sample(items, SAMPLE_N)
    ok = top3 = 0
    rr = 0.0
    for roman, native in items:
        ranked = ro.rank(roman, blob, uni, stems, attested, floor, pfx)
        texts = [t for t, _a, _b in ranked]
        if texts and texts[0] == native:
            ok += 1
            top3 += 1
            rr += 1.0
        else:
            if native in texts[:3]:
                top3 += 1
            if native in texts:
                rr += 1.0 / (texts.index(native) + 1)
    n = len(items)
    payload = {
        "report": "held_out_agree",
        "n": n,
        "top1": ok,
        "top1_pct": round(100 * ok / n, 2) if n else 0,
        "top3": top3,
        "top3_pct": round(100 * top3 / n, 2) if n else 0,
        "mrr": round(rr / n, 4) if n else 0,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
