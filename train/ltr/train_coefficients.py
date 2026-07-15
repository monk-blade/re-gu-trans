#!/usr/bin/env python3
"""Validate coefficient schema / train pairwise logistic ranking from Apple captures.

Without captures: validate + write stub coefficients (CI: coefficient schema validation).
With ≥1000 captures: pairwise logistic updates on CandidateRecord-like features.
Learned scores apply only inside the evidence pool at runtime (ltr.enabled still false
until held-out shows ≥10% relative gain).
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
    "transform_cost",
    "user_count",
]


def feats(roman: str, native: str, meta: dict) -> dict[str, float]:
    """Production CandidateRecord-like features — never include word identity."""
    w = float(meta.get("weight") or 0)
    return {
        "soft": 1.0 if 0 < w < 100 else 0.0,
        "strong": 1.0 if w >= 100 else 0.0,
        "stem_derived": 1.0 if meta.get("source") in ("stem_matra", "stem_postfix", "stem_inflection", "stem_derived") else 0.0,
        "phonetic": 1.0 if meta.get("source") in (None, "phonetic") else 0.0,
        "log_uni": math.log1p(meta.get("uni") or 0),
        "log_weight": math.log1p(max(0.0, w)),
        "attested": 1.0 if meta.get("attested") else 0.0,
        "roman_len_ratio": len(native) / max(1, len(roman)),
        "transform_cost": float(meta.get("transform_cost") or 0),
        "user_count": float(meta.get("user_count") or 0),
    }


def sigmoid(x: float) -> float:
    if x >= 20:
        return 1.0
    if x <= -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def ndcg_at_k(ranked: list[str], gold: str, k: int = 6) -> float:
    if gold not in ranked[:k]:
        return 0.0
    return 1.0 / math.log2(ranked.index(gold) + 2)


def validate_schema(coeffs: dict) -> None:
    assert "weights" in coeffs and "features" in coeffs
    for k in coeffs["features"]:
        assert k in coeffs["weights"], f"missing weight for {k}"
    banned = ("word", "roman_id", "native_id", "per_word")
    for k in coeffs["weights"]:
        assert not any(b in k for b in banned), f"banned identity feature {k}"


def main() -> int:
    coeffs = {
        "version": 2,
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
            "transform_cost": -0.15,
            "user_count": 0.3,
        },
        "features": FEATURE_NAMES,
        "scope": "evidence_pool_only",
        "enabled_gate": "held_out relative +10% top-1 or NDCG with integrity intact",
        "note": "Stub/global coefficients; pairwise logistic when captures exist",
    }
    validate_schema(coeffs)

    report: dict = {"captures": 0, "trained": False, "mode": "coefficient_schema_validation"}

    if CAP.exists():
        import rank_offline as ro

        blob = ro.load_blob()
        uni = ro.load_unigram()
        stems = ro.load_stems()
        attested, floor = ro.load_attested()
        pfx = ro.build_prefix_index(blob.get("lexicon") or {})

        rows = [json.loads(line) for line in CAP.read_text(encoding="utf-8").splitlines() if line.strip()]
        report["captures"] = len(rows)
        report["mode"] = "pairwise_logistic"

        def bucket(roman: str) -> str:
            h = sum(ord(c) for c in roman) % 10
            if h < 8:
                return "train"
            if h == 8:
                return "val"
            return "test"

        grads: dict[str, float] = defaultdict(float)
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
            if any(a in texts[:6] for a in apple[:6]):
                recall6 += 1

            cand_feats = []
            weights = blob.get("weights") or {}
            lex = blob.get("lexicon") or {}
            for t in texts[:8]:
                meta = {
                    "weight": float(weights.get(roman, 0) or 0) if lex.get(roman) == t else 50,
                    "uni": uni.get(t, 0),
                    "attested": t in attested,
                    "source": "strict" if lex.get(roman) == t else "phonetic",
                    "transform_cost": 0.0,
                    "user_count": 0,
                }
                if t != lex.get(roman):
                    meta["source"] = "stem_derived" if t.endswith(("માં", "થી", "ની")) else meta["source"]
                cand_feats.append((t, feats(roman, t, meta)))

            def score(fv: dict[str, float]) -> float:
                s = coeffs["bias"]
                for k, w in coeffs["weights"].items():
                    s += fv.get(k, 0) * w
                return s

            scored = sorted(cand_feats, key=lambda x: -score(x[1]))
            model_texts = [t for t, _ in scored]
            if model_texts and model_texts[0] == gold:
                model_top1 += 1
            model_ndcg += ndcg_at_k(model_texts, gold, 6)

            if bucket(roman) != "train" and report["captures"] >= 1000:
                continue
            gold_fv = next((fv for t, fv in cand_feats if t == gold), None)
            if gold_fv is None:
                continue
            for t, fv in cand_feats:
                if t == gold:
                    continue
                margin = score(gold_fv) - score(fv)
                p = sigmoid(margin)
                for k in FEATURE_NAMES:
                    grads[k] += (p - 1.0) * (gold_fv.get(k, 0) - fv.get(k, 0))
                n_pairs += 1

        if n_pairs:
            lr = 0.08 / max(1, n_pairs)
            for k in FEATURE_NAMES:
                coeffs["weights"][k] = coeffs["weights"].get(k, 0) - lr * grads[k]
            coeffs["note"] = f"Pairwise logistic on {len(rows)} captures; pairs={n_pairs}"
            report["trained"] = True
            validate_schema(coeffs)

        report.update(
            {
                "n": n,
                "baseline_top1_pct": round(100 * base_top1 / n, 2) if n else 0,
                "baseline_ndcg6": round(base_ndcg / n, 4) if n else 0,
                "model_top1_pct": round(100 * model_top1 / n, 2) if n else 0,
                "model_ndcg6": round(model_ndcg / n, 4) if n else 0,
                "apple_recall_at_6_pct": round(100 * recall6 / n, 2) if n else 0,
                "ltr_enabled": False,
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
