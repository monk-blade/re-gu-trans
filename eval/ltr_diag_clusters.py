#!/usr/bin/env python3
"""Cluster ranking diagnostics for Apple-capture disagreements."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAP = ROOT / "data" / "apple_captures" / "menus.jsonl"
OUT = ROOT / "eval" / "ltr_diag_clusters.json"
sys.path.insert(0, str(ROOT / "eval"))


def main() -> int:
    if not CAP.exists():
        OUT.write_text(json.dumps({"note": "no captures", "clusters": {}}, indent=2) + "\n")
        print("no captures — wrote empty clusters")
        return 0
    import rank_offline as ro

    blob = ro.load_blob()
    uni = ro.load_unigram()
    stems = ro.load_stems()
    attested, floor = ro.load_attested()
    pfx = ro.build_prefix_index(blob.get("lexicon") or {})
    clusters: Counter[str] = Counter()
    examples: dict[str, list] = {}

    for line in CAP.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        roman = row["roman"]
        apple = row.get("apple") or []
        if not apple:
            continue
        ranked = [t for t, tier, _ in ro.rank(roman, blob, uni, stems, attested, floor, pfx) if tier != ro.TIER_LATIN]
        gold = apple[0]
        if ranked and ranked[0] == gold:
            clusters["ok_top1"] += 1
            continue
        if gold not in ranked[:6]:
            key = "missing"
        else:
            key = "misranked"
            # finer
            w = float((blob.get("weights") or {}).get(roman, 0) or 0)
            if 0 < w < 100 and any(t != gold for t in ranked[:1]):
                # soft lost?
                src_guess = "soft_lost_to_stem" if ranked and ranked[0] != gold else key
                key = src_guess
            if "ા" in gold and "ા" not in (ranked[0] if ranked else ""):
                key = "vowel_length"
            if any(ch in gold for ch in "ટડણળ") and ranked:
                key = "dental_retroflex"
        clusters[key] += 1
        examples.setdefault(key, [])
        if len(examples[key]) < 8:
            examples[key].append({"roman": roman, "apple0": gold, "ours": ranked[:4]})

    payload = {"clusters": dict(clusters), "examples": examples}
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"clusters": dict(clusters)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
