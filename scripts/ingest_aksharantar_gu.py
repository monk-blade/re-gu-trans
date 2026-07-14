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

# Soft lexicon weights (Apple entries typically ≥100; never override Apple keys).
# Frost-style bands by Aksharantar pair count (still <100 → DICT, not EXACT).
SOFT_WEIGHT = 75
SOFT_WEIGHT_MID = 80
SOFT_WEIGHT_HIGH = 85
# Cap soft OOV keys (stem-eligible first).
MAX_SOFT_KEYS = 300_000
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


def is_soft_weight(w: float | int) -> bool:
    try:
        v = float(w)
    except (TypeError, ValueError):
        return False
    return 0 < v < 100


def soft_weight_for_count(
    cnt: int,
    native_fanin: int = 0,
    *,
    multi_source: bool = False,
    native_freq: int = 0,
    morph_penalty: bool = False,
) -> int:
    """Provenance-aware soft confidence band (still <100 → never EXACT)."""
    evidence = max(int(cnt or 0), int(native_fanin or 0))
    if morph_penalty:
        evidence = max(0, evidence - 5)
    if multi_source or native_freq >= 500 or evidence >= 40 or cnt >= 8:
        return SOFT_WEIGHT_HIGH
    if native_freq >= 50 or evidence >= 8 or cnt >= 2:
        return SOFT_WEIGHT_MID
    return SOFT_WEIGHT


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


def parse_guj_zip(zpath: Path) -> tuple[dict[str, tuple[str, int]], set[str], dict[str, int]]:
    """Return roman→(native, count), natives, and native→roman fan-in."""
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
    native_fanin: dict[str, int] = defaultdict(int)
    for roman, (native, _cnt) in best.items():
        native_fanin[native] += 1
    return best, natives, native_fanin


def load_pairs_tsv(path: Path) -> tuple[dict[str, tuple[str, int]], set[str], dict[str, int]]:
    """roman → (native, pair_cnt); also native → distinct-roman fan-in."""
    best: dict[str, tuple[str, int]] = {}
    natives: set[str] = set()
    native_fanin: dict[str, int] = defaultdict(int)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 2:
            continue
        roman, native = parts[0].lower(), nfc(parts[1])
        cnt = 1
        if len(parts) >= 3:
            try:
                cnt = int(float(parts[2]))
            except ValueError:
                cnt = 1
        if not is_roman(roman) or not is_gujarati(native):
            continue
        prev = best.get(roman)
        if prev is None or cnt > prev[1]:
            best[roman] = (native, cnt)
        natives.add(native)
        native_fanin[native] += 1
    return best, natives, native_fanin


def merge_soft_lexicon(
    best: dict[str, tuple[str, int]],
    max_soft: int,
    native_fanin: dict[str, int] | None = None,
    exclude_romans: set[str] | None = None,
) -> tuple[int, dict[str, int]]:
    """Additive soft-fill: prune bad soft postfix, keep good soft, add bare-stem OOV up to cap.

    Never overrides Apple / non-soft keys (weight >= 100). Soft bands 75/80/85 by evidence.
    Test-split romans (exclude_romans) are never soft-filled.
    """
    if not BLOB_PATH.exists():
        raise SystemExit(f"missing {BLOB_PATH}")
    fanin = native_fanin or {}
    blocked = {r.lower() for r in (exclude_romans or set())}
    blob = json.loads(BLOB_PATH.read_text(encoding="utf-8"))
    lex: dict = blob.setdefault("lexicon", {})
    weights: dict = blob.setdefault("weights", {})

    Soft_MAX_NATIVE_LEN = 16
    purged_postfix = 0
    purged_long = 0
    upgraded = 0

    # Phase 1 — prune soft keys that violate stem/length policy (keep good soft like vinash).
    native_set = set(lex.values())
    for roman in [k for k, w in list(weights.items()) if is_soft_weight(w)]:
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

    # Phase 1b — upgrade soft bands from Aksharantar evidence (same native, higher weight).
    for roman, (native, cnt) in best.items():
        if roman not in lex:
            continue
        cur = float(weights.get(roman, 0) or 0)
        if not is_soft_weight(cur):
            continue
        if lex.get(roman) != native:
            continue
        nw = soft_weight_for_count(cnt, fanin.get(native, 0))
        if nw > cur:
            weights[roman] = nw
            upgraded += 1

    # Refresh native set after prune.
    native_set = set(lex.values())
    soft_count = sum(1 for w in weights.values() if is_soft_weight(w))
    skipped_existing = 0
    skipped_postfix = 0
    added_bare = 0
    added_other = 0
    band_counts = {SOFT_WEIGHT: 0, SOFT_WEIGHT_MID: 0, SOFT_WEIGHT_HIGH: 0}

    # Phase 2 — add missing bare stems first (growth), then orphan postfix if room.
    ranked = sorted(
        best.items(),
        key=lambda x: (
            0 if is_bare_stem_native(x[1][0]) else 1,
            -max(x[1][1], fanin.get(x[1][0], 0)),
            x[0],
        ),
    )
    for roman, (native, cnt) in ranked:
        if soft_count >= max_soft:
            break
        if roman in blocked:
            continue
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
        sw = soft_weight_for_count(cnt, fanin.get(native, 0))
        lex[roman] = native
        weights[roman] = sw
        native_set.add(native)
        soft_count += 1
        band_counts[sw] = band_counts.get(sw, 0) + 1
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
    blob["aksharantar_soft_upgraded"] = upgraded
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
        "upgraded_bands": upgraded,
        "band_added": band_counts,
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
        best, natives, native_fanin = load_pairs_tsv(OUT_PAIRS)
        print(f"loaded cache {OUT_PAIRS}: romans={len(best)} natives={len(natives)}")
    else:
        zpath = download_zip(EXT / "aksharantar_guj.zip")
        best, natives, native_fanin = parse_guj_zip(zpath)
        print(f"aksharantar unique romans={len(best)} natives={len(natives)}")
        with OUT_PAIRS.open("w", encoding="utf-8") as f:
            for roman, (native, cnt) in sorted(best.items(), key=lambda x: -x[1][1]):
                f.write(f"{roman}\t{native}\t{cnt}\n")
        OUT_NATIVE.write_text("\n".join(sorted(natives)) + "\n", encoding="utf-8")
        print(f"wrote {OUT_PAIRS} and {OUT_NATIVE}")

    exclude: set[str] = set()
    split_path = DATA / "splits" / "test_romans.json"
    if split_path.exists():
        try:
            exclude = set(json.loads(split_path.read_text(encoding="utf-8")))
            print(f"excluding {len(exclude)} test-split romans from soft-fill")
        except Exception as e:
            print(f"WARN: could not load {split_path}: {e}")

    added, stats = merge_soft_lexicon(best, args.max_soft, native_fanin, exclude_romans=exclude)
    print(
        f"soft-fill: +{added} (bare={stats['added_bare']} orphan_pf={stats['added_postfix_orphan']}) "
        f"soft_total={stats['soft_total']}/{stats['cap']} "
        f"purged_pf={stats['purged_postfix']} purged_long={stats['purged_long']} "
        f"upgraded={stats['upgraded_bands']} bands_added={stats['band_added']} "
        f"skipped_pf={stats['skipped_postfix_stem_known']}"
    )
    if not args.skip_lm:
        merge_into_lm(natives)
    print("done — run scripts/filter_lexicon_quality.py then sync_rime + eval")


if __name__ == "__main__":
    main()
