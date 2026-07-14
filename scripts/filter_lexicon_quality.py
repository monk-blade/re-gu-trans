#!/usr/bin/env python3
"""Filter gu_lexicon_blob.json for word-quality ranking.

Goals (no per-word baking):
- Drop multi-word / sentence-like natives (spaces), except short greetings kept via allowlist.
- Drop ultra-long soft natives (soft weight < STRONG).
- Drop soft stem+postposition duplicates when the bare stem native is already in the lexicon
  (મૂલ્યમાં when મૂલ્ય exists) — runtime stem_postfix synthesizes these.
- Soft-fill must never override Apple-weight keys (ingest already skips; ranking demotes
  native morph extensions of strong typed stems).

Writes in-place by default; also emits data/quality/lexicon_filter_stats.json.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOB = ROOT / "rime" / "gu_lexicon_blob.json"
STATS = ROOT / "data" / "quality" / "lexicon_filter_stats.json"

STRONG = 100
SOFT_MAX_NATIVE_LEN = 16
HARD_MAX_NATIVE_LEN = 28

PHRASE_ALLOW = {
    "jay-hind",
    "jay-gujaraat",
    "jay-gujarat",
    "kem-chho",
    "kem-cho",
    "subh-prabhaat",
    "shubh-prabhat",
    "janmadin-mubarak",
    "maaf-karjo",
    "hardik-aabhinamdan",
    "hum-maajaa-maa",
}

GU_POSTFIXES = [
    "માંથી",
    "વાળું",
    "વાળી",
    "વાળા",
    "વાળો",
    "માં",
    "થી",
    "ની",
    "નું",
    "નાં",
    "ના",
    "ને",
    "નો",
]


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def strip_postfix(gu: str) -> str | None:
    for pf in GU_POSTFIXES:
        if gu.endswith(pf) and len(gu) > len(pf) + 1:
            return gu[: -len(pf)]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--blob", type=Path, default=BLOB)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep-phrases", action="store_true", default=True)
    args = ap.parse_args()

    blob = json.loads(args.blob.read_text(encoding="utf-8"))
    lex: dict[str, str] = {nfc(k): nfc(v) for k, v in blob.get("lexicon", {}).items()}
    weights: dict[str, float] = {nfc(k): float(v) for k, v in blob.get("weights", {}).items()}
    exceptions = blob.get("exceptions") or {}

    native_set = set(lex.values())
    reasons: Counter[str] = Counter()
    drop: list[tuple[str, str, str]] = []

    for roman, gu in list(lex.items()):
        wt = weights.get(roman, STRONG)
        soft = wt < STRONG

        if " " in gu or "\u00a0" in gu:
            if args.keep_phrases and roman in PHRASE_ALLOW:
                continue
            if soft or roman not in PHRASE_ALLOW:
                drop.append((roman, gu, "space"))
                reasons["space"] += 1
                continue

        if soft and len(gu) > SOFT_MAX_NATIVE_LEN:
            drop.append((roman, gu, "soft_long"))
            reasons["soft_long"] += 1
            continue
        if len(gu) > HARD_MAX_NATIVE_LEN:
            drop.append((roman, gu, "hard_long"))
            reasons["hard_long"] += 1
            continue

        if soft:
            stem = strip_postfix(gu)
            if stem and stem in native_set:
                drop.append((roman, gu, "soft_postfix_dup"))
                reasons["soft_postfix_dup"] += 1
                continue

    for roman, _gu, _why in drop:
        lex.pop(roman, None)
        weights.pop(roman, None)

    stats = {
        "before": len(blob.get("lexicon", {})),
        "after": len(lex),
        "dropped": len(drop),
        "reasons": dict(reasons),
        "sample_drop": drop[:40],
    }
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: stats[k] for k in ("before", "after", "dropped", "reasons")}, ensure_ascii=False))

    if args.dry_run:
        print("dry-run: blob not written")
        return 0

    out = {
        "exceptions": exceptions,
        "lexicon": dict(sorted(lex.items())),
        "weights": {k: weights[k] for k in sorted(weights) if k in lex},
    }
    # Preserve ingest metadata (aksharantar_soft_* etc.).
    for k, v in blob.items():
        if k not in out:
            out[k] = v
    args.blob.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {args.blob}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
