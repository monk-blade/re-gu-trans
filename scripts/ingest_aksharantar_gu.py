#!/usr/bin/env python3
"""Ingest Aksharantar Gujarati (guj) roman↔native pairs for soft lexicon + LM fill.

- Never overrides Apple lexicon keys/weights in rime/gu_lexicon_blob.json
- Soft-fills missing roman→native with low weight
- Prefer bare stems; skip soft postfix natives when the stem is already known
  (runtime stem_postfix synthesizes મૂલ્યમાં from મૂલ્ય)
- Boosts native forms into unigram floor only (does NOT expand attested.json;
  quality attested comes from scripts/build_gu_word_freq.py)

Dataset: https://huggingface.co/datasets/ai4bharat/Aksharantar (guj.zip)
Packaging of mined data: CC0 (see HF card). We do not redistribute the full zip;
caches live under data/external/ (gitignored).
"""
from __future__ import annotations

import argparse
import json
import unicodedata
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EXT = DATA / "external"
BLOB_PATH = ROOT / "rime" / "gu_lexicon_blob.json"
OUT_PAIRS = EXT / "aksharantar_gu_pairs.tsv"
OUT_NATIVE = EXT / "aksharantar_gu_native.txt"

HF_URL = "https://huggingface.co/datasets/ai4bharat/Aksharantar/resolve/main/guj.zip"

# Soft lexicon weight (Apple entries typically ≥100; never override Apple keys)
SOFT_WEIGHT = 75
# Cap soft OOV keys (stem-eligible first). Higher than legacy 120k for useful coverage.
MAX_SOFT_KEYS = 180_000
ATTESTED_FLOOR = 50

# Same postpositions as scripts/filter_lexicon_quality.py (longest first).
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


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())


def is_gujarati(w: str) -> bool:
    return bool(w) and any("\u0A80" <= ch <= "\u0AFF" for ch in w)


def is_roman(w: str) -> bool:
    if not w or len(w) > 32 or len(w) < 2:
        return False
    return all(("a" <= c <= "z") or c in ".'-" for c in w.lower()) and any(c.isalpha() for c in w)


def strip_postfix(gu: str) -> str | None:
    for pf in GU_POSTFIXES:
        if gu.endswith(pf) and len(gu) > len(pf) + 1:
            return gu[: -len(pf)]
    return None


def is_bare_stem_native(gu: str) -> bool:
    return strip_postfix(gu) is None


def download_zip(cache: Path) -> Path:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.stat().st_size > 1_000_000:
        return cache
    print(f"fetch {HF_URL}")
    req = urllib.request.Request(HF_URL, headers={"User-Agent": "Mozilla/5.0 re-gu-trans/2.8"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        cache.write_bytes(resp.read())
    print(f"cached {cache} ({cache.stat().st_size} bytes)")
    return cache


def parse_guj_zip(zpath: Path) -> tuple[dict[str, tuple[str, int]], set[str]]:
    """Return roman→(native, count) and set of native words."""
    pair_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    natives: set[str] = set()

    with zipfile.ZipFile(zpath, "r") as zf:
        print(f"zip members sample: {zf.namelist()[:8]} … total={len(zf.namelist())}")
        for name in zf.namelist():
            if name.endswith("/") or "/." in name:
                continue
            lower = name.lower()
            if not (lower.endswith(".jsonl") or "train" in lower or "valid" in lower or "test" in lower):
                if not lower.endswith(".json"):
                    continue
            with zf.open(name) as fh:
                raw = fh.read()
            try:
                text = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                native = nfc(str(row.get("native") or row.get("native word") or row.get("word") or ""))
                english = nfc(str(row.get("english") or row.get("english word") or row.get("roman") or ""))
                if not native and not english:
                    vals = list(row.values())
                    if len(vals) >= 2:
                        a, b = str(vals[0]), str(vals[1])
                        if is_gujarati(a) and is_roman(b):
                            native, english = nfc(a), nfc(b)
                        elif is_gujarati(b) and is_roman(a):
                            native, english = nfc(b), nfc(a)
                if not is_gujarati(native) or not is_roman(english):
                    continue
                roman = english.lower()
                pair_counts[roman][native] += 1
                natives.add(native)

    best: dict[str, tuple[str, int]] = {}
    for roman, choices in pair_counts.items():
        native, cnt = max(choices.items(), key=lambda x: x[1])
        best[roman] = (native, cnt)
    return best, natives


def load_pairs_tsv(path: Path) -> tuple[dict[str, tuple[str, int]], set[str]]:
    best: dict[str, tuple[str, int]] = {}
    natives: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        roman, native = parts[0].lower(), nfc(parts[1])
        cnt = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 1
        if not is_roman(roman) or not is_gujarati(native):
            continue
        prev = best.get(roman)
        if prev is None or cnt > prev[1]:
            best[roman] = (native, cnt)
        natives.add(native)
    return best, natives


def merge_soft_lexicon(best: dict[str, tuple[str, int]], max_soft: int) -> tuple[int, dict[str, int]]:
    """Additive soft-fill: prune bad soft postfix, keep good soft, add bare-stem OOV up to cap.

    Never overrides Apple / non-soft keys (weight != SOFT_WEIGHT).
    """
    if not BLOB_PATH.exists():
        raise SystemExit(f"missing {BLOB_PATH}")
    blob = json.loads(BLOB_PATH.read_text(encoding="utf-8"))
    lex: dict = blob.setdefault("lexicon", {})
    weights: dict = blob.setdefault("weights", {})

    Soft_MAX_NATIVE_LEN = 16
    purged_postfix = 0
    purged_long = 0

    # Phase 1 — prune soft keys that violate stem/length policy (keep good soft like vinash).
    native_set = set(lex.values())
    for roman in [k for k, w in list(weights.items()) if int(w) == SOFT_WEIGHT]:
        gu = lex.get(roman) or ""
        if " " in gu or "\u00a0" in gu or len(gu) > Soft_MAX_NATIVE_LEN:
            lex.pop(roman, None)
            weights.pop(roman, None)
            purged_long += 1
            continue
        stem = strip_postfix(gu)
        if stem and stem in native_set and stem != gu:
            lex.pop(roman, None)
            weights.pop(roman, None)
            purged_postfix += 1

    # Refresh native set after prune.
    native_set = set(lex.values())
    soft_count = sum(1 for w in weights.values() if int(w) == SOFT_WEIGHT)
    skipped_existing = 0
    skipped_postfix = 0
    added_bare = 0
    added_other = 0

    # Phase 2 — add missing bare stems first (growth), then orphan postfix if room.
    ranked = sorted(
        best.items(),
        key=lambda x: (0 if is_bare_stem_native(x[1][0]) else 1, -x[1][1], x[0]),
    )
    for roman, (native, _cnt) in ranked:
        if soft_count >= max_soft:
            break
        if roman in lex:
            skipped_existing += 1
            continue  # never override Apple / existing soft
        stem = strip_postfix(native)
        if stem and stem in native_set:
            skipped_postfix += 1
            continue
        # Prefer bare stems until soft budget is mostly used; allow orphan postfix near the end.
        if stem is not None and soft_count < int(max_soft * 0.92):
            continue
        if " " in native or len(native) > Soft_MAX_NATIVE_LEN:
            continue
        lex[roman] = native
        weights[roman] = SOFT_WEIGHT
        native_set.add(native)
        soft_count += 1
        if stem is None:
            added_bare += 1
        else:
            added_other += 1

    added = added_bare + added_other
    blob["lexicon"] = lex
    blob["weights"] = weights
    blob["aksharantar_soft_keys"] = soft_count
    blob["aksharantar_soft_bare_added"] = added_bare
    blob["aksharantar_soft_skipped_postfix"] = skipped_postfix
    blob["aksharantar_soft_purged_postfix"] = purged_postfix
    BLOB_PATH.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    data_blob = DATA / "gu_lexicon_blob.json"
    data_blob.parent.mkdir(parents=True, exist_ok=True)
    data_blob.write_bytes(BLOB_PATH.read_bytes())
    stats = {
        "added": added,
        "added_bare": added_bare,
        "added_postfix_orphan": added_other,
        "skipped_postfix_stem_known": skipped_postfix,
        "skipped_existing": skipped_existing,
        "purged_postfix": purged_postfix,
        "purged_long": purged_long,
        "soft_total": soft_count,
        "cap": max_soft,
    }
    return added, stats


def merge_into_lm(natives: set[str]) -> None:
    """Boost natives into unigram floor only — do NOT expand attested (quality policy)."""
    lm = ROOT / "rime" / "js" / "lm"
    uni_path = lm / "unigram.tsv"
    if not uni_path.exists():
        print("WARN: unigram missing; run scripts/build_gu_word_freq.py first")
        return

    counts: dict[str, int] = {}
    for line in uni_path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1].isdigit():
            counts[parts[0]] = int(parts[1])

    # Prefer bare stems into the floor set; still boost orphan postfix if stem unknown.
    native_set = set(counts)
    boosted = 0
    for w in sorted(natives):
        stem = strip_postfix(w)
        if stem and stem in native_set:
            continue
        counts[w] = max(counts.get(w, 0), ATTESTED_FLOOR)
        native_set.add(w)
        boosted += 1

    lines = [f"{w}\t{c}" for w, c in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    uni_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    lm_alt = ROOT / "rime" / "lm" / "unigram.tsv"
    if lm_alt.parent.exists():
        lm_alt.write_text(uni_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(
        f"unigram boosted with {boosted}/{len(natives)} aksharantar natives "
        f"(floor={ATTESTED_FLOOR}, postfix skipped when stem known); attested untouched"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--from-cache",
        action="store_true",
        help="Use data/external/aksharantar_gu_pairs.tsv (skip zip fetch/parse)",
    )
    ap.add_argument("--max-soft", type=int, default=MAX_SOFT_KEYS, help="Soft OOV key cap")
    ap.add_argument("--skip-lm", action="store_true", help="Do not boost unigram floor")
    args = ap.parse_args()

    EXT.mkdir(parents=True, exist_ok=True)

    if args.from_cache and OUT_PAIRS.exists():
        best, natives = load_pairs_tsv(OUT_PAIRS)
        print(f"loaded cache {OUT_PAIRS}: romans={len(best)} natives={len(natives)}")
    else:
        zpath = download_zip(EXT / "aksharantar_guj.zip")
        best, natives = parse_guj_zip(zpath)
        print(f"aksharantar unique romans={len(best)} natives={len(natives)}")
        with OUT_PAIRS.open("w", encoding="utf-8") as f:
            for roman, (native, cnt) in sorted(best.items(), key=lambda x: -x[1][1]):
                f.write(f"{roman}\t{native}\t{cnt}\n")
        OUT_NATIVE.write_text("\n".join(sorted(natives)) + "\n", encoding="utf-8")
        print(f"wrote {OUT_PAIRS} and {OUT_NATIVE}")

    added, stats = merge_soft_lexicon(best, args.max_soft)
    print(
        f"soft-fill: +{added} (bare={stats['added_bare']} orphan_pf={stats['added_postfix_orphan']}) "
        f"soft_total={stats['soft_total']}/{stats['cap']} "
        f"purged_pf={stats['purged_postfix']} purged_long={stats['purged_long']} "
        f"skipped_pf={stats['skipped_postfix_stem_known']} weight={SOFT_WEIGHT}"
    )
    if not args.skip_lm:
        merge_into_lm(natives)
    print("done — run scripts/filter_lexicon_quality.py then sync_rime + eval")


if __name__ == "__main__":
    main()
