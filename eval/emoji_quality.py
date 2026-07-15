#!/usr/bin/env python3
"""Validate emoji data hygiene, first-page intent recall, and negative precision."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path

from production_rank import top_six_many

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "emoji_quality_summary.json"


def stable(value: str) -> str:
    return hashlib.sha256(("emoji-quality-v1\t" + value).encode()).hexdigest()


def looks_emoji(text: str) -> bool:
    return any(
        0x1F000 <= ord(ch) <= 0x1FAFF or
        0x2600 <= ord(ch) <= 0x27BF or
        0x1F1E6 <= ord(ch) <= 0x1F1FF
        for ch in text
    )


def valid_sequence(text: str) -> bool:
    return bool(text) and "\ufffd" not in text and not text.startswith(("\ufe0e", "\ufe0f", "\u200d")) and not text.endswith("\u200d") and not any(unicodedata.category(ch) in {"Cc", "Cs"} for ch in text)


def main() -> int:
    payload = json.loads((ROOT / "rime" / "js" / "emoji_keywords.json").read_text(encoding="utf-8"))
    keywords = payload.get("keywords") or {}
    invalid = []
    for code, items in keywords.items():
        for item in items:
            if not valid_sequence(str(item.get("emoji") or "")):
                invalid.append({"code": code, "emoji": item.get("emoji")})
        if len(code) <= 2 and not any(item.get("source") in {"curated_gu", "gu_extra"} for item in items):
            invalid.append({"code": code, "reason": "uncurated-short-key"})

    positive = sorted(
        ((code, items) for code, items in keywords.items() if any(float(item.get("confidence") or 0) >= 0.90 for item in items)),
        key=lambda row: stable(row[0]),
    )[:1_000]
    positive_menus = top_six_many([code for code, _items in positive])
    visible = 0
    for (_code, items), menu in zip(positive, positive_menus, strict=True):
        expected = {str(item["emoji"]) for item in items if float(item.get("confidence") or 0) >= 0.90}
        visible += int(bool(expected.intersection(menu)))

    blob = json.loads((ROOT / "rime" / "js" / "gu_lexicon_blob.json").read_text(encoding="utf-8"))
    negative_keys = sorted((key for key in (blob.get("lexicon") or {}) if key not in keywords), key=stable)[:5_000]
    negative_menus = top_six_many(negative_keys)
    false_positive = sum(any(looks_emoji(item) for item in menu) for menu in negative_menus)
    report = {
        "report": "emoji_quality",
        "schema_version": payload.get("version"),
        "keywords": len(keywords),
        "positive_cases": len(positive),
        "first_page_recall_pct": round(100 * visible / len(positive), 2) if positive else None,
        "negative_cases": len(negative_keys),
        "false_positive_pct": round(100 * false_positive / len(negative_keys), 3) if negative_keys else None,
        "invalid_sequences": invalid,
        "ok": payload.get("version") == 2 and len(positive) >= 1_000 and len(negative_keys) >= 5_000 and not invalid and visible / max(1, len(positive)) >= 0.85 and false_positive / max(1, len(negative_keys)) <= 0.01,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
