#!/usr/bin/env python3
"""Load shared ranking_policy.json for offline eval / tooling."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "rime" / "js" / "ranking_policy.json"
_CACHE: dict | None = None


def load_policy() -> dict:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if POLICY.exists():
        _CACHE = json.loads(POLICY.read_text(encoding="utf-8"))
    else:
        _CACHE = {
            "version": 1,
            "weights": {"lexicon_strong": 100, "user_learning_threshold": 3},
        }
    return _CACHE
