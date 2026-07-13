#!/usr/bin/env python3
"""Build a scalable Gujarati native-script frequency dictionary for IME rescoring.

Sources (same idea as IndicXlit dictionary rescoring / macOS LM):
  1. Apple-distilled lexicon values + weights (from re-gu-trans blob/tsv)
  2. Google i18n wordcounts: http://www.gstatic.com/i18n/corpora/wordcounts/gu.txt
  3. Indic Keyboard priorities: jishnu7/dictionaries languages/gu/wordfreq.txt

Output:
  rime/js/lm/unigram.tsv     — word\\tcount  (loaded by gujarati_translator.js)
  rime/js/lm/stems.json      — stem → max_count for morphology boost (ફાવ + શે)
"""
from __future__ import annotations

import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "rime" / "js" / "lm"
DATA = ROOT / "data"

GOOGLE_URL = "http://www.gstatic.com/i18n/corpora/wordcounts/gu.txt"
INDIC_URL = "https://raw.githubusercontent.com/jishnu7/dictionaries/master/languages/gu/wordfreq.txt"

# Common Gujarati inflectional / verbal endings to derive stems
SUFFIXES = [
    "વાળાઓ", "વાળીઓ", "વાળું", "વાળી", "વાળા", "વાળો",
    "ીઓ", "ાઓ", "ોને", "ાને", "ીને", "ુંને",
    "માંથી", "માં", "થી", "ની", "નો", "ના", "ને", "નું", "નાં",
    "શે", "શો", "શું", "ીશ", "ીશું", "શે?",
    "્યો", "્યા", "્યું", "ી", "્યો",
    "તો", "તા", "તી", "તું", "તાં",
    "વું", "વા", "વાનું", "વાની", "વાના",
    "ે", "ો", "ા", "ી", "ું", "ાં",
]


def is_gujarati_word(w: str) -> bool:
    return bool(w) and any("\u0A80" <= ch <= "\u0AFF" for ch in w)


def load_apple_counts() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    tsv = DATA / "gu_lexicon.tsv"
    if tsv.exists():
        for line in tsv.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            gu, _roman, w = parts[0], parts[1], int(parts[2])
            if is_gujarati_word(gu):
                counts[gu] = max(counts[gu], w)
    blob = ROOT / "rime" / "gu_lexicon_blob.json"
    if blob.exists():
        data = json.loads(blob.read_text(encoding="utf-8"))
        weights = data.get("weights") or {}
        lex = data.get("lexicon") or {}
        for roman, gu in lex.items():
            if not is_gujarati_word(gu):
                continue
            w = int(weights.get(roman, 100))
            counts[gu] = max(counts[gu], w)
    return dict(counts)


def fetch_text(url: str, cache: Path) -> str:
    if cache.exists() and cache.stat().st_size > 1000:
        return cache.read_text(encoding="utf-8", errors="ignore")
    print(f"fetch {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 re-gu-trans/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        raise SystemExit(f"Failed to fetch {url}: {e}\nPlace file at {cache} and re-run.") from e
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def load_google_counts() -> dict[str, int]:
    text = fetch_text(GOOGLE_URL, DATA / "external" / "gu_google_wordcounts.txt")
    counts: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 2:
            continue
        # format: count\\tword  OR word\\tcount — Google uses count\\tword
        a, b = parts[0], parts[1]
        if a.isdigit() and is_gujarati_word(b):
            counts[b] = max(counts.get(b, 0), int(a))
        elif b.isdigit() and is_gujarati_word(a):
            counts[a] = max(counts.get(a, 0), int(b))
    return counts


def load_indic_counts() -> dict[str, int]:
    text = fetch_text(INDIC_URL, DATA / "external" / "gu_indic_wordfreq.txt")
    counts: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        # word count
        word, raw = parts[0], parts[-1]
        if not raw.isdigit() or not is_gujarati_word(word):
            continue
        counts[word] = max(counts.get(word, 0), int(raw))
    return counts


def merge_counts(*dicts: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for d in dicts:
        for w, c in d.items():
            # scale-normalize roughly: take max after light scaling
            out[w] = max(out[w], int(c))
    return dict(out)


def build_stems(word_counts: dict[str, int]) -> dict[str, int]:
    """Map stem → max frequency of any word sharing that stem."""
    stems: dict[str, int] = defaultdict(int)
    for word, c in word_counts.items():
        stems[word] = max(stems[word], c)
        for suf in SUFFIXES:
            if len(word) > len(suf) + 1 and word.endswith(suf):
                stem = word[: -len(suf)]
                if stem:
                    stems[stem] = max(stems[stem], c)
    return dict(stems)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    apple = load_apple_counts()
    google = load_google_counts()
    indic = load_indic_counts()
    print(f"apple words={len(apple)} google={len(google)} indic={len(indic)}")

    # Weighted merge: keep strongest evidence; boost Apple lexicon membership
    merged: dict[str, int] = {}
    for w, c in google.items():
        merged[w] = max(merged.get(w, 0), c)
    for w, c in indic.items():
        # indic counts are larger scale; compress a bit
        merged[w] = max(merged.get(w, 0), max(c // 10, 1))
    for w, c in apple.items():
        # Apple-attested words get at least 200 so they beat pure phonetics
        merged[w] = max(merged.get(w, 0), c * 2 if c >= 100 else max(c, 200))

    stems = build_stems(merged)
    lines = [f"{w}\t{c}" for w, c in sorted(merged.items(), key=lambda x: (-x[1], x[0]))]
    uni = OUT_DIR / "unigram.tsv"
    uni.write_text("\n".join(lines) + "\n", encoding="utf-8")
    stem_path = OUT_DIR / "stems.json"
    # keep top stems only for size
    top_stems = dict(sorted(stems.items(), key=lambda x: -x[1])[:80000])
    stem_path.write_text(json.dumps(top_stems, ensure_ascii=False), encoding="utf-8")

    # also copy next to ~/ sync location via rime/
    (ROOT / "rime" / "lm").mkdir(exist_ok=True)
    (ROOT / "rime" / "lm" / "unigram.tsv").write_text(uni.read_text(encoding="utf-8"), encoding="utf-8")
    (ROOT / "rime" / "lm" / "stems.json").write_bytes(stem_path.read_bytes())

    for probe in ["જમીન", "કેમ", "ફાવે", "ફાવશે", "ફાવો", "ગુજરાત"]:
        print(f"  {probe}: count={merged.get(probe, 0)} stem={stems.get(probe.rstrip('શેેોાીું'), 0)}")

    # stem check for ફાવશે
    print(f"stem ફાવ -> {stems.get('ફાવ', 0)}")
    print(f"wrote {uni} ({len(merged)} words), {stem_path} ({len(top_stems)} stems)")


if __name__ == "__main__":
    main()
