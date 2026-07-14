#!/usr/bin/env python3
"""Ingest AI4Bharat IndicXlit Gujarati word vocabulary into data/external/.

Source (local, not committed):
  ~/Downloads/gujarati/gu_words_a4b.json   (~900k natives)
  ~/Downloads/gujarati/gu_scripts.json    (glyph table; optional)
  ~/Downloads/gujarati/gu_101_model.pth   (IndicXlit weights — NEVER commit; hot-path reject)

Writes:
  data/external/a4b_gu_natives.txt          — filtered natives (one per line)
  data/external/a4b_gu_ingest_stats.json    — counts

Prefer bare stems: skip natives ending in common postpositions when the stem is
already in the A4B set (મૂલ્યમાં when મૂલ્ય exists). Unigram soft floor comes from
scripts/build_gu_word_freq.py; this list is stem-quality native coverage.

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


def strip_postfix(gu: str) -> str | None:
    for pf in GU_POSTFIXES:
        if gu.endswith(pf) and len(gu) > len(pf) + 1:
            return gu[: -len(pf)]
    return None


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

    scripts = src_dir / "gu_scripts.json"
    if scripts.exists():
        shutil.copy2(scripts, EXT / "a4b_gu_scripts.json")

    pth = src_dir / "gu_101_model.pth"
    pth_note = None
    if pth.exists():
        pth_note = str(pth)
        print(f"NOTE: IndicXlit checkpoint present at {pth} (not copied; not for hot path)")

    raw = json.loads(src.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        print(f"ERROR: expected JSON list in {src}, got {type(raw)}")
        return 2

    filtered = {w for w in raw if is_quality_gu(w)}
    # Prefer bare stems over postfix morphs when stem already in the set.
    bare_first = sorted(filtered, key=lambda w: (0 if strip_postfix(w) is None else 1, len(w), w))
    kept: list[str] = []
    seen: set[str] = set()
    skipped_postfix = 0
    for w in bare_first:
        stem = strip_postfix(w)
        if stem and stem in seen:
            skipped_postfix += 1
            continue
        kept.append(w)
        seen.add(w)

    max_new = int(os.environ.get("A4B_MAX_NEW", "250000"))
    ranked = sorted(
        kept,
        key=lambda w: (0 if 3 <= len(w) <= 14 else 1, 0 if strip_postfix(w) is None else 1, len(w), w),
    )
    if len(ranked) > max_new:
        ranked = ranked[:max_new]

    OUT.write_text("\n".join(ranked) + "\n", encoding="utf-8")
    stats = {
        "source": str(src),
        "raw": len(raw),
        "filtered_quality": len(filtered),
        "skipped_postfix_stem_known": skipped_postfix,
        "kept_before_cap": len(kept),
        "written": len(ranked),
        "cap": max_new,
        "out": str(OUT.relative_to(ROOT)),
        "indicxlit_pth": pth_note,
        "hot_path_model": False,
        "stem_prefer": True,
    }
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"a4b gu natives: raw={stats['raw']} quality={stats['filtered_quality']} "
        f"skip_postfix={skipped_postfix} wrote={stats['written']} -> {OUT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
