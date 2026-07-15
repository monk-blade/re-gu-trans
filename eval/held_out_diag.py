#!/usr/bin/env python3
"""Held-out diagnostic: missing vs below-6 vs wrong-order."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))
import rank_offline as ro  # noqa: E402
from production_rank import top_six_many  # noqa: E402

FROZEN_GOLD = ROOT / "data" / "splits" / "held_out_gold.jsonl"
OUT = ROOT / "eval" / "held_out_diag.json"
VOWELS = set("અઆઇઈઉઊઋએઐઑઓઔાિીુૂૃેૈૉોૌ")


def consonant_skeleton(text: str) -> str:
    return "".join(ch for ch in text if ch not in VOWELS and ch not in "ંઁ")


def failure_signals(roman: str, gold: str, menu: list[str]) -> list[str]:
    top = menu[0] if menu else ""
    signals = []
    if top and consonant_skeleton(top) == consonant_skeleton(gold) and top != gold:
        signals.append("vowel_length")
    if any(token in roman for token in ("kh", "gh", "chh", "jh", "th", "dh", "ph", "bh")):
        signals.append("aspiration")
    if re.search(r"[tTdDnNlL]", roman) or any(ch in gold for ch in "ટઠડઢણળ"):
        signals.append("dental_retroflex")
    if re.search(r"(?:ng|ny|[nmM])", roman) or any(ch in gold for ch in "ંઁનમણઙઞ"):
        signals.append("nasal_anusvara")
    if "્" in gold:
        signals.append("conjunct_virama")
    if re.search(r"(?:ma|maa|manthi|thi|ni|no|na|ne|nu|nun|va|vu|ta|ti|to|tu|she|sho)$", roman):
        signals.append("suffix_morphology")
    if re.search(r"(?:tion|sion|sch|ck|qu|oo|ee)|[cqxfz]", roman):
        signals.append("loanword_spelling")
    return signals or ["unknown"]


def main() -> int:
    if not FROZEN_GOLD.exists():
        print(f"missing {FROZEN_GOLD}", file=sys.stderr)
        return 2
    gold: dict[str, str] = {}
    for line in FROZEN_GOLD.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        roman = (row.get("input") or row.get("roman") or "").lower()
        native = row.get("gold") or row.get("native")
        if not native and row.get("candidates"):
            native = row["candidates"][0].get("text")
        if roman and native:
            gold[roman] = native

    blob = ro.load_blob()
    lex = blob.get("lexicon") or {}
    eligible = [(r, n) for r, n in gold.items() if r not in lex]
    items = eligible

    missing = below6 = wrong_order = hit_top1 = 0
    samples = {"missing": [], "below6": [], "wrong_order": []}
    primary_clusters: Counter[str] = Counter()
    signal_clusters: Counter[str] = Counter()
    cluster_examples: dict[str, list[dict]] = defaultdict(list)
    menus = top_six_many([roman for roman, _native in items])
    for (roman, native), texts in zip(items, menus, strict=True):
        failure = None
        if native not in texts:
            missing += 1
            failure = "missing"
            if len(samples["missing"]) < 25:
                samples["missing"].append({"roman": roman, "gold": native, "menu": texts[:6]})
        elif native not in texts[:6]:
            below6 += 1
            failure = "below6"
            if len(samples["below6"]) < 25:
                samples["below6"].append(
                    {"roman": roman, "gold": native, "rank": texts.index(native) + 1, "menu": texts[:8]}
                )
        elif texts[0] != native:
            wrong_order += 1
            failure = "wrong_order"
            if len(samples["wrong_order"]) < 25:
                samples["wrong_order"].append(
                    {"roman": roman, "gold": native, "top1": texts[0], "menu": texts[:6]}
                )
        else:
            hit_top1 += 1
        if failure:
            signals = failure_signals(roman, native, texts)
            primary_clusters[signals[0]] += 1
            signal_clusters.update(signals)
            for signal in signals:
                if len(cluster_examples[signal]) < 8:
                    cluster_examples[signal].append(
                        {"roman": roman, "gold": native, "menu": texts[:6], "failure": failure}
                    )

    n = len(items)
    report = {
        "evaluated": n,
        "eligible_pool": len(eligible),
        "missing_from_candidates": missing,
        "generated_but_below_6": below6,
        "in_top6_wrong_order": wrong_order,
        "top1_correct": hit_top1,
        "missing_pct": round(100.0 * missing / max(1, n), 2),
        "below6_pct": round(100.0 * below6 / max(1, n), 2),
        "wrong_order_pct": round(100.0 * wrong_order / max(1, n), 2),
        "top1_pct": round(100.0 * hit_top1 / max(1, n), 2),
        "recall_at_6_pct": round(100.0 * (n - missing - below6) / max(1, n), 2),
        "classified_failures": missing + below6 + wrong_order,
        "clusters": {
            "primary": dict(primary_clusters.most_common()),
            "signals": dict(signal_clusters.most_common()),
            "examples": dict(cluster_examples),
        },
        "samples": samples,
        "gates": {
            "recall_at_6_target_pct": 60,
            "top1_target_pct": 45,
            "top3_target_pct": 55,
            "ndcg_at_6_target": 0.5,
        },
        "note": "Frost-style: raise recall via generation/data before LTR. Soft weight floors are not equivalent across sources.",
        "ranker": "production-javascript-trie",
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    console_report = {k: v for k, v in report.items() if k not in {"samples", "clusters"}}
    console_report["cluster_primary"] = report["clusters"]["primary"]
    console_report["cluster_signals"] = report["clusters"]["signals"]
    print(json.dumps(console_report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
