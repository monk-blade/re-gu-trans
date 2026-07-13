#!/usr/bin/env python3
"""Ingest Aksharantar Gujarati (guj) roman↔native pairs for soft lexicon + LM fill.

- Never overrides Apple lexicon keys/weights in rime/gu_lexicon_blob.json
- Soft-fills missing roman→native with low weight
- Boosts native forms into unigram floor only (does NOT expand attested.json;
  quality attested comes from scripts/build_gu_word_freq.py)

Dataset: https://huggingface.co/datasets/ai4bharat/Aksharantar (guj.zip)
Packaging of mined data: CC0 (see HF card). We do not redistribute the full zip;
caches live under data/external/ (gitignored).
"""
from __future__ import annotations

import io
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
# Cap new roman keys to keep blob size reasonable
MAX_SOFT_KEYS = 120_000
ATTESTED_FLOOR = 50


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())


def is_gujarati(w: str) -> bool:
    return bool(w) and any("\u0A80" <= ch <= "\u0AFF" for ch in w)


def is_roman(w: str) -> bool:
    if not w or len(w) > 32 or len(w) < 2:
        return False
    return all(("a" <= c <= "z") or c in ".'-" for c in w.lower()) and any(c.isalpha() for c in w)


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
        names = [n for n in zf.namelist() if n.endswith(".jsonl") or n.endswith(".json")]
        if not names:
            # sometimes nested
            names = [n for n in zf.namelist() if "train" in n.lower() or n.endswith(".jsonl")]
        print(f"zip members sample: {zf.namelist()[:8]} … total={len(zf.namelist())}")
        for name in zf.namelist():
            if not (name.endswith(".jsonl") or name.endswith(".json") or "train" in name):
                # read all text-ish
                if "/." in name or name.endswith("/"):
                    continue
            lower = name.lower()
            if not (lower.endswith(".jsonl") or "train" in lower or "valid" in lower or "test" in lower):
                if not lower.endswith(".json"):
                    continue
            with zf.open(name) as fh:
                # try line-delimited JSON
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
                # HF fields: native / english (or similar)
                native = nfc(str(row.get("native") or row.get("native word") or row.get("word") or ""))
                english = nfc(str(row.get("english") or row.get("english word") or row.get("roman") or ""))
                if not native and not english:
                    # alternate keys
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


def merge_soft_lexicon(best: dict[str, tuple[str, int]]) -> int:
    if not BLOB_PATH.exists():
        raise SystemExit(f"missing {BLOB_PATH}")
    blob = json.loads(BLOB_PATH.read_text(encoding="utf-8"))
    lex: dict = blob.setdefault("lexicon", {})
    weights: dict = blob.setdefault("weights", {})

    # Idempotent re-runs: strip prior soft-fill only (weight==SOFT_WEIGHT).
    # Never touch Apple / other non-soft keys.
    for roman in [k for k, w in weights.items() if int(w) == SOFT_WEIGHT]:
        lex.pop(roman, None)
        weights.pop(roman, None)

    added = 0
    # Prefer higher pair counts first; cap total soft keys
    ranked = sorted(best.items(), key=lambda x: -x[1][1])
    for roman, (native, _cnt) in ranked:
        if added >= MAX_SOFT_KEYS:
            break
        if roman in lex:
            continue  # never override Apple / existing
        lex[roman] = native
        weights[roman] = SOFT_WEIGHT
        added += 1
    blob["lexicon"] = lex
    blob["weights"] = weights
    blob["aksharantar_soft_keys"] = added
    BLOB_PATH.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    data_blob = DATA / "gu_lexicon_blob.json"
    data_blob.write_bytes(BLOB_PATH.read_bytes())
    return added


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

    for w in natives:
        counts[w] = max(counts.get(w, 0), ATTESTED_FLOOR)

    lines = [f"{w}\t{c}" for w, c in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
    uni_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "rime" / "lm" / "unigram.tsv").write_text(uni_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"unigram boosted with {len(natives)} aksharantar natives (floor={ATTESTED_FLOOR}); attested untouched")


def main() -> None:
    EXT.mkdir(parents=True, exist_ok=True)
    zpath = download_zip(EXT / "aksharantar_guj.zip")
    best, natives = parse_guj_zip(zpath)
    print(f"aksharantar unique romans={len(best)} natives={len(natives)}")

    # Cache TSV for rebuilds / audit
    with OUT_PAIRS.open("w", encoding="utf-8") as f:
        for roman, (native, cnt) in sorted(best.items(), key=lambda x: -x[1][1]):
            f.write(f"{roman}\t{native}\t{cnt}\n")
    OUT_NATIVE.write_text("\n".join(sorted(natives)) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PAIRS} and {OUT_NATIVE}")

    added = merge_soft_lexicon(best)
    print(f"soft-filled lexicon keys={added} (weight={SOFT_WEIGHT}, cap={MAX_SOFT_KEYS})")
    merge_into_lm(natives)
    print("done — run scripts/build_gu_word_freq.py to refresh attested; then sync_rime + eval")


if __name__ == "__main__":
    main()
