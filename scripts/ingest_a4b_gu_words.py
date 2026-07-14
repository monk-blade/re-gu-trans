#!/usr/bin/env python3
"""Ingest AI4Bharat IndicXlit Gujarati word vocabulary into data/external/.

Source (local, not committed):
  ~/Downloads/gujarati/gu_words_a4b.json   (~900k natives)
  ~/Downloads/gujarati/gu_scripts.json    (glyph table; optional)
  ~/Downloads/gujarati/gu_101_model.pth   (IndicXlit weights — NEVER commit; hot-path reject)

Writes:
  data/external/a4b_gu_natives.txt          — filtered natives (one per line)
  data/external/a4b_gu_ingest_stats.json    — counts

Env:
  A4B_GU_DIR   override source directory (default: ~/Downloads/gujarati)
  A4B_GU_JSON  override path to gu_words_a4b.json
  A4B_MAX_NEW  cap filtered list size (default 250000; prefer len 3–14)
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "external"
OUT = EXT / "a4b_gu_natives.txt"
STATS = EXT / "a4b_gu_ingest_stats.json"

DEFAULT_DIR = Path.home() / "Downloads" / "gujarati"


def is_quality_gu(w: str) -> bool:
    if not w or not isinstance(w, str):
        return False
    if not (2 <= len(w) <= 30):
        return False
    # Gujarati block only
    if any(ord(c) < 0x0A80 or ord(c) > 0x0AFF for c in w):
        return False
    first = ord(w[0])
    # Must start with independent vowel or consonant (not candrabindu/anusvara/matra/virama)
    if not ((0x0A85 <= first <= 0x0A91) or (0x0A95 <= first <= 0x0AB9)):
        return False
    # At least one consonant
    if not any(0x0A95 <= ord(c) <= 0x0AB9 for c in w):
        return False
    return True


def main() -> int:
    EXT.mkdir(parents=True, exist_ok=True)
    src_dir = Path(os.environ.get("A4B_GU_DIR", str(DEFAULT_DIR)))
    src = Path(os.environ.get("A4B_GU_JSON", str(src_dir / "gu_words_a4b.json")))
    if not src.exists():
        print(f"ERROR: missing {src}")
        print("Place AI4Bharat gu_words_a4b.json under ~/Downloads/gujarati/ or set A4B_GU_JSON")
        return 2

    # Optional: stash scripts.json next to natives (still gitignored under external/)
    scripts = src_dir / "gu_scripts.json"
    if scripts.exists():
        shutil.copy2(scripts, EXT / "a4b_gu_scripts.json")

    pth = src_dir / "gu_101_model.pth"
    pth_note = None
    if pth.exists():
        # Do not copy 40MB checkpoint into the repo tree by default.
        pth_note = str(pth)
        print(f"NOTE: IndicXlit checkpoint present at {pth} (not copied; not for hot path)")

    raw = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print(f"ERROR: expected JSON list in {src}, got {type(raw)}")
        return 2

    filtered = sorted({w for w in raw if is_quality_gu(w)})
    # Prefer mid-length everyday words when capping
    max_new = int(os.environ.get("A4B_MAX_NEW", "250000"))
    ranked = sorted(filtered, key=lambda w: (0 if 3 <= len(w) <= 14 else 1, len(w), w))
    if len(ranked) > max_new:
        ranked = ranked[:max_new]

    OUT.write_text("\n".join(ranked) + "\n", encoding="utf-8")
    stats = {
        "source": str(src),
        "raw": len(raw),
        "filtered_quality": len(filtered),
        "written": len(ranked),
        "cap": max_new,
        "out": str(OUT.relative_to(ROOT)),
        "indicxlit_pth": pth_note,
        "hot_path_model": False,
    }
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"a4b gu natives: raw={stats['raw']} quality={stats['filtered_quality']} wrote={stats['written']} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
