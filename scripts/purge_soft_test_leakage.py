#!/usr/bin/env python3
"""Remove soft lexicon keys that collide with the frozen test roman split.

Keeps strong (weight ≥100) keys even if roman is in the test set (integrity).
Rewrites rime/js/gu_lexicon_blob.json (+ legacy mirrors).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS_BLOB = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
ROOT_BLOB = ROOT / "rime" / "gu_lexicon_blob.json"
DATA_BLOB = ROOT / "data" / "gu_lexicon_blob.json"
TEST = ROOT / "data" / "splits" / "test_romans.json"
STRONG = 100


def main() -> int:
    path = JS_BLOB if JS_BLOB.exists() else ROOT_BLOB
    if not path.exists():
        print(f"missing {path}")
        return 2
    test = set(json.loads(TEST.read_text(encoding="utf-8"))) if TEST.exists() else set()
    blob = json.loads(path.read_text(encoding="utf-8"))
    lex = blob.get("lexicon") or {}
    weights = blob.get("weights") or {}
    dropped_soft = dropped_strong_report = 0
    for roman in list(lex.keys()):
        if roman not in test:
            continue
        w = float(weights.get(roman, STRONG) or STRONG)
        if 0 < w < STRONG:
            lex.pop(roman, None)
            weights.pop(roman, None)
            dropped_soft += 1
        else:
            dropped_strong_report += 1  # keep strong; report overlap only
    soft = sum(1 for w in weights.values() if 0 < float(w or 0) < STRONG)
    out = json.dumps({**blob, "lexicon": lex, "weights": weights}, ensure_ascii=False, separators=(",", ":"))
    for dest in (JS_BLOB, ROOT_BLOB, DATA_BLOB):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(out, encoding="utf-8")
    print(
        json.dumps(
            {
                "dropped_soft_test": dropped_soft,
                "strong_test_overlap_kept": dropped_strong_report,
                "soft_remaining": soft,
                "lex_total": len(lex),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
