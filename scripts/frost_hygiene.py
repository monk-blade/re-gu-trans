#!/usr/bin/env python3
"""Frost-inspired lexicon hygiene (method only — no GPL code/data).

1) Drop malformed / rare / non-word soft entries
2) Optionally re-normalize soft weights using quality corpus evidence

Delegates hard filters to filter_lexicon_quality.py; records provenance note.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOB = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
OUT = ROOT / "data" / "quality" / "frost_hygiene_stats.json"


def main() -> int:
    # Reuse existing quality filter (no GPL)
    rc = subprocess.call([sys.executable, str(ROOT / "scripts" / "filter_lexicon_quality.py")])
    blob = {}
    if BLOB.exists():
        blob = json.loads(BLOB.read_text(encoding="utf-8"))
    weights = blob.get("weights") or {}
    soft = sum(1 for w in weights.values() if 0 < float(w or 0) < 100)
    strong = sum(1 for w in weights.values() if float(w or 0) >= 100)
    stats = {
        "filter_rc": rc,
        "soft_keys": soft,
        "strong_keys": strong,
        "provenance": blob.get("provenance"),
        "note": "Rime Frost pattern: clean noise then normalize; do not equate soft floors across sources",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(stats, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
