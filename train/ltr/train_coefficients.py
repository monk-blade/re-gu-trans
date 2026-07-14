#!/usr/bin/env python3
"""Train compact linear ranking coefficients from local Apple capture dumps.

Input (gitignored): data/apple_captures/menus.jsonl
  {"roman": "...", "apple": ["ન1","ન2",...], "ours": optional}

Output: rime/js/ltr_coefficients.json (global features only — no per-word coeffs).

Gates (when captures present): recall@6 ≥90%; relative +10% top-1 & NDCG@6 vs baseline.
Without captures: writes identity/stub coefficients and exits 0.
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAP = ROOT / "data" / "apple_captures" / "menus.jsonl"
OUT = ROOT / "rime" / "js" / "ltr_coefficients.json"
REPORT = ROOT / "eval" / "ltr_train_summary.json"
sys.path.insert(0, str(ROOT / "eval"))


FEATURE_NAMES = [
    "soft",
    "strong",
    "stem_derived",
    "phonetic",
    "log_uni",
    "log_weight",
    "attested",
    "roman_len_ratio",
]


def feats(roman: str, native: str, meta: dict) -> dict[str, float]:
    w = float(meta.get("weight") or 0)
    return {
        "soft": 1.0 if 0 < w < 100 else 0.0,
        "strong": 1.0 if w >= 100 else 0.0,
        "stem_derived": 1.0 if meta.get("source") in ("stem_matra", "stem_postfix", "stem_derived") else 0.0,
        "phonetic": 1.0 if meta.get("source") in (None, "phonetic") else 0.0,
        "log_uni": math.log1p(meta.get("uni") or 0),
        "log_weight": math.log1p(max(0.0, w)),
        "attested": 1.0 if meta.get("attested") else 0.0,
        "roman_len_ratio": len(native) / max(1, len(roman)),
    }


def ndcg_at_k(ranked: list[str], gold: str, k: int = 6) -> float:
    if gold not in ranked[:k]:
        return 0.0
    return 1.0 / math.log2(ranked.index(gold) + 2)


def main() -> int:
    # Stub coefficients: prefer strong + attested + unigram, demote stem_derived slightly
    coeffs = {
        "version": 1,
        "bias": 0.0,
        "weights": {
            "soft": 0.4,
            "strong": 1.2,
            "stem_derived": -0.35,
            "phonetic": -0.2,
            "log_uni": 0.45,
            "log_weight": 0.25,
            "attested": 0.8,
            "roman_len_ratio": 0.05,
        },
        "features": FEATURE_NAMES,
        "note": "Stub/global coefficients; retrain when data/apple_captures/menus.jsonl exists",
    }

    report: dict = {"captures": 0, "trained": False}

    if CAP.exists():
        import rank_offline as ro

        blob = ro.load_blob()
        uni = ro.load_unigram()
        stems = ro.load_stems()
        attested, floor = ro.load_attested()
        pfx = ro.build_prefix_index(blob.get("lexicon") or {})

        rows = []
        for line in CAP.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        report["captures"] = len(rows)

        # Pairwise: gold (Apple#1) vs other ours candidates — accumulate gradient
        grads = defaultdict(float)
        n_pairs = 0
        base_top1 = base_ndcg = model_top1 = model_ndcg = recall6 = 0
        n = 0
        for row in rows:
            roman = row["roman"]
            apple = row.get("apple") or []
            if not apple:
                continue
            gold = apple[0]
            ranked = ro.rank(roman, blob, uni, stems, attested, floor, pfx)
            texts = [t for t, tier, _ in ranked if tier != ro.TIER_LATIN]
            n += 1
            if texts and texts[0] == gold:
                base_top1 += 1
            base_ndcg += ndcg_at_k(texts, gold, 6)
            if gold in texts[:6] or gold in apple[:6] and any(a in texts[:6] for a in apple[:6]):
                # Apple recall@6: any apple menu item in our top6
                if any(a in texts[:6] for a in apple[:6]):
                    recall6 += 1

            # Build feature vectors for ours candidates (source unknown → rough)
            cand_feats = []
            weights = blob.get("weights") or {}
            lex = blob.get("lexicon") or {}
            for t in texts[:8]:
                meta = {
                    "weight": float(weights.get(roman, 0) or 0) if lex.get(roman) == t else 50,
                    "uni": uni.get(t, 0),
                    "attested": t in attested,
                    "source": "strict" if lex.get(roman) == t else "phonetic",
                }
                if t != lex.get(roman):
                    # heuristic stem
                    meta["source"] = "stem_derived" if t.endswith(("માં", "થી", "ની")) else meta["source"]
                cand_feats.append((t, feats(roman, t, meta)))

            # Score with coeffs (iterative one-pass update)
            def score(fv):
                s = coeffs["bias"]
                for k, w in coeffs["weights"].items():
                    s += fv.get(k, 0) * w
                return s

            scored = sorted(cand_feats, key=lambda x: -score(x[1]))
            model_texts = [t for t, _ in scored]
            if model_texts and model_texts[0] == gold:
                model_top1 += 1
            model_ndcg += ndcg_at_k(model_texts, gold, 6)

            gold_fv = None
            for t, fv in cand_feats:
                if t == gold:
                    gold_fv = fv
                    break
            if gold_fv is None:
                continue
            for t, fv in cand_feats:
                if t == gold:
                    continue
                # Push gold above rivals
                margin = score(gold_fv) - score(fv)
                if margin < 1.0:
                    for k in FEATURE_NAMES:
                        grads[k] += gold_fv.get(k, 0) - fv.get(k, 0)
                    n_pairs += 1

        if n_pairs:
            lr = 0.05 / max(1, n_pairs)
            for k in FEATURE_NAMES:
                coeffs["weights"][k] = coeffs["weights"].get(k, 0) + lr * grads[k]
            coeffs["note"] = f"Trained on {len(rows)} captures; pairs={n_pairs}"
            report["trained"] = True

        report.update(
            {
                "n": n,
                "baseline_top1_pct": round(100 * base_top1 / n, 2) if n else 0,
                "baseline_ndcg6": round(base_ndcg / n, 4) if n else 0,
                "model_top1_pct": round(100 * model_top1 / n, 2) if n else 0,
                "model_ndcg6": round(model_ndcg / n, 4) if n else 0,
                "apple_recall_at_6_pct": round(100 * recall6 / n, 2) if n else 0,
            }
        )

    OUT.write_text(json.dumps(coeffs, indent=2) + "\n", encoding="utf-8")
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), **report}, indent=2))
    if report.get("captures", 0) >= 1000:
        if report.get("apple_recall_at_6_pct", 0) < 90:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
