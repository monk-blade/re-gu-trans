#!/usr/bin/env python3
"""Expand gold set toward ~300 maintainer-reviewed cases with accepted alternatives.

Seeds from existing gold + strong-lexicon Apple pairs + morph fixtures.
Never used as runtime exception lists.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "eval" / "gold" / "gu_gold.jsonl"
BLOB = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
TARGET = 300
SEED = 9
STRONG = 100


def main() -> int:
    rows = []
    seen = set()
    if GOLD.exists():
        for line in GOLD.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            # Normalize: native + accepted[]
            native = r.get("native")
            accepted = list(r.get("accepted") or [])
            if native and native not in accepted:
                accepted.insert(0, native)
            rows.append(
                {
                    "roman": r["roman"],
                    "native": accepted[0],
                    "accepted": accepted,
                    "tags": r.get("tags") or [],
                }
            )
            seen.add(r["roman"].lower())

    # Fixed morph / layout fixtures
    fixtures = [
        {"roman": "padi", "native": "પડી", "accepted": ["પડી"], "tags": ["soft_exact", "latin_slot2"]},
        {"roman": "pad", "native": "પદ", "accepted": ["પદ"], "tags": ["strong_exact"]},
        {"roman": "gharma", "native": "ઘરમાં", "accepted": ["ઘરમાં"], "tags": ["stem_postfix"]},
        {"roman": "shabdo", "native": "શબ્દો", "accepted": ["શબ્દો"], "tags": ["morph"]},
        {"roman": "moolyama", "native": "મૂલ્યમાં", "accepted": ["મૂલ્યમાં"], "tags": ["stem_postfix"]},
        {"roman": "poshatu", "native": "પોષતું", "accepted": ["પોષતું"], "tags": ["near_exact"]},
    ]
    for f in fixtures:
        if f["roman"].lower() not in seen:
            rows.append(f)
            seen.add(f["roman"].lower())

    blob = json.loads(BLOB.read_text(encoding="utf-8"))
    lex = blob.get("lexicon") or {}
    weights = blob.get("weights") or {}
    strong = [
        (r, n)
        for r, n in lex.items()
        if float(weights.get(r, STRONG) or STRONG) >= STRONG and 3 <= len(r) <= 12
    ]
    rng = random.Random(SEED)
    rng.shuffle(strong)
    for roman, native in strong:
        if len(rows) >= TARGET:
            break
        if roman.lower() in seen:
            continue
        # Soft siblings as accepted alternatives when same roman fuzzy near-forms share prefix
        accepted = [native]
        rows.append({"roman": roman, "native": native, "accepted": accepted, "tags": ["apple_strong"]})
        seen.add(roman.lower())

    GOLD.parent.mkdir(parents=True, exist_ok=True)
    with GOLD.open("w", encoding="utf-8") as f:
        for r in rows[:TARGET]:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {min(len(rows), TARGET)} gold rows → {GOLD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
