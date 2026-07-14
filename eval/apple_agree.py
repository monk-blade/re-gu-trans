#!/usr/bin/env python3
"""Top-1 agreement vs cached Apple labels in data/gu_train.jsonl.

Uses eval.rank_offline.rank (full offline mirror). Writes gitignored dumps:
  eval/apple_agree_summary.json
  eval/apple_disagree.jsonl
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
SUMMARY = ROOT / "eval" / "apple_agree_summary.json"
DISAGREE = ROOT / "eval" / "apple_disagree.jsonl"


def load_train() -> list[dict]:
    rows = []
    if not TRAIN.exists():
        return rows
    for line in TRAIN.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cands = row.get("candidates") or []
        if not cands:
            continue
        rows.append(row)
    return rows


def main() -> int:
    rows = load_train()
    if not rows:
        print(f"missing/empty {TRAIN}", file=sys.stderr)
        return 2

    blob = ro.load_blob()
    uni = ro.load_unigram()
    stems = ro.load_stems()
    attested, floor = ro.load_attested()
    prefix_index = ro.build_prefix_index(blob.get("lexicon") or {})

    match = 0
    by_len: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [ok, total]
    disagree_fh = DISAGREE.open("w", encoding="utf-8")

    for row in rows:
        inp = str(row.get("input") or "").strip()
        apple = row["candidates"][0]["text"]
        ranked = ro.rank(inp, blob, uni, stems, attested, floor, prefix_index)
        ours = ranked[0][0] if ranked else None
        tier = ranked[0][1] if ranked else None
        ok = ours == apple
        if ok:
            match += 1
        bucket = "1-3" if len(inp) <= 3 else ("4-6" if len(inp) <= 6 else ("7-10" if len(inp) <= 10 else "11+"))
        by_len[bucket][1] += 1
        if ok:
            by_len[bucket][0] += 1
        if not ok:
            disagree_fh.write(
                json.dumps(
                    {
                        "roman": inp,
                        "ours": ours,
                        "ours_tier": tier,
                        "apple": apple,
                        "apple_alts": [c.get("text") for c in row["candidates"][:5]],
                        "ours_top5": [t for t, _, _ in ranked[:5]],
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    disagree_fh.close()
    n = len(rows)
    summary = {
        "n": n,
        "match": match,
        "pct": round(100.0 * match / n, 2) if n else 0.0,
        "by_length": {
            k: {"ok": v[0], "n": v[1], "pct": round(100.0 * v[0] / v[1], 2) if v[1] else 0.0}
            for k, v in sorted(by_len.items())
        },
        "disagree_path": str(DISAGREE.relative_to(ROOT)),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"apple agree: {match}/{n} = {summary['pct']}%")
    print(f"wrote {SUMMARY}")
    print(f"wrote {DISAGREE} ({n - match} disagreements)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
