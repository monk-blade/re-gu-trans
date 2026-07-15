#!/usr/bin/env python3
"""Release-quality aggregate report (quality + runtime + payload + capabilities)."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "release_quality_report.json"


def load_json(path: Path):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    quality_env = os.environ.copy()
    # Aggregate first, then apply release-only gates below so the authoritative
    # report is still written when the Apple-class ratchet fails.
    quality_env.pop("REQUIRE_APPLE_CLASS", None)
    fresh = subprocess.run(
        [sys.executable, "eval/quality_report.py"], cwd=ROOT, env=quality_env, check=False
    )
    if fresh.returncode:
        return fresh.returncode
    js = ROOT / "rime" / "js"
    quality = load_json(ROOT / "eval" / "quality_report.json") or {}
    held = load_json(ROOT / "eval" / "held_out_agree_summary.json") or {}
    gold = load_json(ROOT / "eval" / "gold_agree_summary.json") or {}
    apple = load_json(ROOT / "eval" / "apple_integrity_summary.json") or {}
    parity = load_json(ROOT / "eval" / "js_parity_summary.json") or {}
    learning = load_json(ROOT / "eval" / "learning_integration_summary.json") or {}
    harness = load_json(ROOT / "eval" / "rime_harness_summary.json") or {}
    bench = load_json(ROOT / "eval" / "bench_summary.json") or {}
    budget = load_json(ROOT / "eval" / "budget_summary.json") or {}
    apple_class = load_json(ROOT / "eval" / "apple_class_quality_summary.json") or {}
    emoji_quality = load_json(ROOT / "eval" / "emoji_quality_summary.json") or {}
    neural_model = load_json(ROOT / "eval" / "neural_model_benchmark_summary.json") or {}
    report = {
        "project": "Akshar GU",
        "package_id": "re-gu-trans",
        "version": (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        if (ROOT / "VERSION").exists()
        else None,
        "quality": {
            "held_out": load_json(ROOT / "eval" / "held_out_agree_summary.json"),
            "held_out_diag": load_json(ROOT / "eval" / "held_out_diag.json"),
            "gold": load_json(ROOT / "eval" / "gold_agree_summary.json"),
            "apple_integrity": load_json(ROOT / "eval" / "apple_integrity_summary.json"),
            "quality_report": quality,
            "apple_class": apple_class or None,
            "emoji": emoji_quality or None,
            "neural_model": neural_model or None,
        },
        "runtime": budget,
        "parity": parity,
        "learning": learning,
        "benchmark": bench,
        "ltr": load_json(ROOT / "eval" / "ltr_train_summary.json"),
        "harness": harness or None,
        "payload_hashes": {
            "lexicon.trie.bin": sha256(js / "lexicon.trie.bin"),
            "prefix.trie.bin": sha256(js / "prefix.trie.bin"),
            "native_lm.trie.bin": sha256(js / "native_lm.trie.bin"),
            "native_lm_meta.json": sha256(js / "native_lm_meta.json"),
            "ranking_policy.json": sha256(js / "ranking_policy.json"),
        },
        "capabilities": {
            "binary_tries": all(
                (js / n).exists()
                for n in ("lexicon.trie.bin", "prefix.trie.bin", "native_lm.trie.bin")
            ),
            "require_binary_tries": os.environ.get("REQUIRE_BINARY_TRIES", "1"),
            "ltr_enabled": False,
            "neural_model": (harness.get("capabilities") or {}).get("neural_model") is True,
            "observed_runtime": harness.get("capabilities") or None,
            "writeFileAtomic": (harness.get("capabilities") or {}).get("write_file_atomic"),
            "librime_pin": "1.16.1",
            "librime_qjs_tag": "v1.3.0",
        },
        "gates": {
            "smoke": "48/48",
            "recall_at_6_pct": 42.35,
            "top1_pct": 34.3,
            "apple_integrity_pct": 99.6,
            "gold_pct": 100,
            "js_binary_text_parity_pct": 100,
            "learning_integration": True,
            "non_finite_scores": 0,
            "package_mb": 70,
            "startup_ms": 1000,
            "heap_mb": 150,
            "query_p95_ms": 5,
            "beam": 64,
            "apple_class_core": {"top1_pct": 45, "top3_pct": 55, "recall_at_6_pct": 60},
            "apple_class_hybrid": {"top1_improvement_pp": 5, "recall_at_6_improvement_pp": 8},
            "hybrid_ranking": {
                "top1_pct": 60,
                "top3_pct": 75,
                "recall_at_6_pct": 82,
                "arbitration_regret_pct_below": 5,
            },
            "emoji_first_page_recall_pct": 85,
            "emoji_false_positive_pct": 1,
        },
        "compat_matrix": {
            "librime_1_16_1": "pinned-production",
            "librime_current": "test-before-upgrade",
        },
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUT), "binary_tries": report["capabilities"]["binary_tries"]}, indent=2))
    failures = []
    smoke = quality.get("smoke") or {}
    if smoke.get("ok") != 48 or smoke.get("total") != 48:
        failures.append("smoke")
    if (held.get("top1_pct") or 0) < 34.3:
        failures.append("held_top1")
    if (held.get("recall_at_6_pct") or 0) < 42.35:
        failures.append("held_recall6")
    if (gold.get("pct") or 0) < 100:
        failures.append("gold")
    if (apple.get("pct") or 0) < 99.6:
        failures.append("apple_integrity")
    if parity.get("binary_text_match_rate") != 100.0 or parity.get("non_finite") != 0:
        failures.append("parity")
    if not learning.get("ok"):
        failures.append("learning")
    if os.environ.get("REQUIRE_REAL_RIME") == "1":
        caps = harness.get("capabilities") or {}
        if not harness.get("real_librime") or not harness.get("learning_persisted"):
            failures.append("real_librime")
        if not all(caps.get(name) for name in ("trie", "candidate_access", "commit_notifier", "write_file_atomic")):
            failures.append("runtime_capabilities")
    if bench.get("query_p95_ms") is None or bench.get("query_p95_ms") > 5:
        failures.append("query_p95")
    if budget.get("staged_est_bytes") is None or budget.get("staged_est_bytes") > 70 * 1024 * 1024:
        failures.append("payload")
    if not emoji_quality.get("ok"):
        failures.append("emoji_quality")
    if os.environ.get("REQUIRE_APPLE_CLASS") == "1":
        if not (apple_class.get("core_targets") or {}).get("passed"):
            failures.append("apple_class_core_targets")
        if not (apple_class.get("stress") or {}).get("full_gate"):
            failures.append("apple_class_full_stress")
    if os.environ.get("REQUIRE_HYBRID") == "1":
        if not neural_model.get("passed"):
            failures.append("apple_class_hybrid")
        if not (apple_class.get("stress") or {}).get("full_gate"):
            failures.append("apple_class_full_stress")
        if not (harness.get("capabilities") or {}).get("neural_model") and os.environ.get("REQUIRE_REAL_RIME") == "1":
            failures.append("real_neural_model")
    if os.environ.get("REQUIRE_HYBRID_TARGETS") == "1" and not neural_model.get("quality_targets_met"):
        failures.append("hybrid_ranking_targets")
    report["gate_failures"] = failures
    report["passed"] = not failures
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if failures:
        print("release gates failed: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
