#!/usr/bin/env python3
"""Apple integrity / compatibility report (NOT held-out generalization).

Gold labels come from data/gu_train.jsonl — nearly all romans are already in
the strong lexicon. Use for Apple compatibility regressions only.

Writes: eval/apple_integrity_summary.json, eval/apple_disagree.jsonl
Also refreshes eval/apple_agree_summary.json for backwards compatibility.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

import rank_offline as ro  # noqa: E402

TRAIN = ROOT / "data" / "gu_train.jsonl"
SUMMARY = ROOT / "eval" / "apple_integrity_summary.json"
LEGACY = ROOT / "eval" / "apple_agree_summary.json"
DISAGREE = ROOT / "eval" / "apple_disagree.jsonl"


def load_train() -> list[dict]:
    rows = []
    if not TRAIN.exists():
        return rows
    for line in TRAIN.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not (row.get("candidates") or []):
            continue
        rows.append(row)
    return rows


def main() -> int:
    rows = load_train()
    if not rows:
        print("no train rows", file=sys.stderr)
        return 2
    blob = ro.load_blob()
    uni = ro.load_unigram()
    stems = ro.load_stems()
    attested, floor = ro.load_attested()
    prefix_index = ro.build_prefix_index(blob.get("lexicon") or {})

    n = match = 0
    by_len: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    disagree_fh = DISAGREE.open("w", encoding="utf-8")
    for row in rows:
        roman = str(row.get("input") or row.get("roman") or "").strip().lower()
        cands = row.get("candidates") or []
        apple = cands[0]["text"] if isinstance(cands[0], dict) else cands[0]
        if not roman or not apple:
            continue
        ranked = ro.rank(roman, blob, uni, stems, attested, floor, prefix_index)
        ours = ranked[0][0] if ranked else ""
        ok = ours == apple
        n += 1
        match += int(ok)
        bucket = "1-3" if len(roman) <= 3 else ("4-6" if len(roman) <= 6 else "7-10" if len(roman) <= 10 else "11+")
        by_len[bucket][1] += 1
        by_len[bucket][0] += int(ok)
        if not ok:
            disagree_fh.write(
                json.dumps(
                    {
                        "roman": roman,
                        "ours": ours,
                        "ours_tier": ranked[0][1] if ranked else None,
                        "apple": apple,
                        "apple_alts": [
                            (c["text"] if isinstance(c, dict) else c) for c in cands[:5]
                        ],
                        "ours_top5": [t for t, _tier, _sc in ranked[:5]],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    disagree_fh.close()
    pct = round(100.0 * match / n, 2) if n else 0.0
    payload = {
        "report": "apple_integrity",
        "note": "Integrity vs Apple train labels — not held-out generalization",
        "n": n,
        "match": match,
        "pct": pct,
        "by_length": {
            k: {"ok": v[0], "n": v[1], "pct": round(100.0 * v[0] / v[1], 2) if v[1] else 0}
            for k, v in sorted(by_len.items())
        },
        "disagree_path": str(DISAGREE.relative_to(ROOT)),
    }
    SUMMARY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    LEGACY.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"apple integrity: {match}/{n} = {pct}%")
    print(f"wrote {SUMMARY} and {DISAGREE} ({n - match} disagreements)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
