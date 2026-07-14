#!/usr/bin/env python3
"""Cluster eval/apple_disagree.jsonl into phonetic/ranking rule families."""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DISAGREE = ROOT / "eval" / "apple_disagree.jsonl"
OUT = ROOT / "eval" / "apple_disagree_clusters.json"

ANUSVARA = "\u0A82"
VIRAMA = "\u0ACD"
AA = "\u0ABE"
II = "\u0AC0"
I_MAT = "\u0ABF"
SH = "\u0AB6"
S = "\u0AB8"
UU_NASAL = "\u0AC1" + ANUSVARA

ENGLISH_LOAN_RE = re.compile(
    r"(school|college|doctor|hospital|london|station|computer|email|phone|america|english|friend)",
    re.I,
)


def strip_marks(s: str) -> str:
    return "".join(ch for ch in s if not (0x0A81 <= ord(ch) <= 0x0ACC) and ch != VIRAMA)


def tag(row: dict) -> list[str]:
    roman = row.get("roman") or ""
    ours = row.get("ours") or ""
    apple = row.get("apple") or ""
    tags: list[str] = []

    if ANUSVARA in apple and ANUSVARA not in ours and "ન" in ours:
        tags.append("anusvara_n_stop")
    if apple.count(AA) > ours.count(AA):
        tags.append("long_a")
    if re.search(r"(ai|ay|oi|ui|ei)", roman) and ("ઈ" in apple or "ઇ" in apple):
        tags.append("diphthong_ai_oi_ui")
    if roman.startswith("sh") and apple.startswith(SH) and ours.startswith(S):
        tags.append("typed_sh")
    if "w" in roman and "વ" in apple:
        tags.append("v_w")
    if "z" in roman and ("ઝ" in apple or "જ" in apple):
        tags.append("z_j")
    if apple.count(VIRAMA) != ours.count(VIRAMA):
        tags.append("schwa_vs_conjunct")
    if (II in apple and I_MAT in ours) or (I_MAT in apple and II in ours):
        tags.append("i_length")
    if apple.endswith(UU_NASAL) and not ours.endswith(UU_NASAL):
        tags.append("nasal_final_u")
    if re.search(r"(mm|nn|tt|kk|ll)", roman) and VIRAMA in apple and VIRAMA not in ours:
        tags.append("geminate")
    if ENGLISH_LOAN_RE.search(roman):
        tags.append("english_loan")
    if row.get("ours_tier") == 0 and ours != apple:
        tags.append("soft_lex_win")
    if strip_marks(ours) == strip_marks(apple) and ours != apple:
        tags.append("orthography_glue")  # ં vs ન્ etc.
    if not tags:
        tags.append("other")
    # lexicon_miss: apple never in ours_top5
    top5 = row.get("ours_top5") or []
    if apple and apple not in top5:
        tags.append("lexicon_miss")
    return tags


def main() -> int:
    if not DISAGREE.exists():
        print(f"missing {DISAGREE} — run eval/apple_agree.py first", file=sys.stderr)
        return 2

    clusters: dict[str, list[dict]] = defaultdict(list)
    counts: Counter[str] = Counter()
    n = 0
    for line in DISAGREE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        n += 1
        for t in tag(row):
            counts[t] += 1
            if len(clusters[t]) < 50:
                clusters[t].append(
                    {"roman": row.get("roman"), "ours": row.get("ours"), "apple": row.get("apple")}
                )

    out = {
        "n_disagree": n,
        "counts": dict(counts.most_common()),
        "examples": {k: clusters[k] for k, _ in counts.most_common()},
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"clustered {n} disagreements → {OUT}")
    for k, v in counts.most_common(15):
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
