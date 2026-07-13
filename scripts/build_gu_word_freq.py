#!/usr/bin/env python3
"""Build Gujarati native-script frequency + attested dictionaries for IME rescoring.

Sources (IndicXlit-style dictionary rescoring / macOS LM):
  1. Apple-distilled lexicon values + weights
  2. Google i18n wordcounts (public corpus frequency)
  3. Indic Keyboard priorities
  4. aspell-gu base wordlist (kartikm/gu-wordlist) — production spell dict (GPL-2+)
  5. hunspell gu_IN.dic — LibreOffice / distro spell dict (GPL+)

Output:
  rime/js/lm/unigram.tsv   — word\\tcount
  rime/js/lm/stems.json    — stem → max_count
  rime/js/lm/attested.json — {"words":[...]} spell-correct native forms

Caches under data/external/ (regenerable). Does not use proprietary Google IME binaries.
"""
from __future__ import annotations

import json
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "rime" / "js" / "lm"
DATA = ROOT / "data"
EXT = DATA / "external"

GOOGLE_URL = "http://www.gstatic.com/i18n/corpora/wordcounts/gu.txt"
INDIC_URL = "https://raw.githubusercontent.com/jishnu7/dictionaries/master/languages/gu/wordfreq.txt"
ASPELL_URL = "https://raw.githubusercontent.com/kartikm/gu-wordlist/master/gu-wordlist.txt"
HUNSPELL_URL = "https://raw.githubusercontent.com/elastic/hunspell/master/dicts/gu_IN/gu_IN.dic"

# Floor so spell-correct OOV forms beat invented phonetics in dictionaryValidity
ATTESTED_FLOOR = 50

# Common Gujarati inflectional / verbal endings to derive stems
SUFFIXES = [
    "વાળાઓ", "વાળીઓ", "વાળું", "વાળી", "વાળા", "વાળો",
    "ીઓ", "ાઓ", "ોને", "ાને", "ીને", "ુંને",
    "માંથી", "માં", "થી", "ની", "નો", "ના", "ને", "નું", "નાં",
    "શે", "શો", "શું", "ીશ", "ીશું",
    "્યો", "્યા", "્યું",
    "તો", "તા", "તી", "તું", "તાં",
    "વું", "વા", "વાનું", "વાની", "વાના",
    "ે", "ો", "ા", "ી", "ું", "ાં",
]


def is_gujarati_word(w: str) -> bool:
    return bool(w) and any("\u0A80" <= ch <= "\u0AFF" for ch in w)


def nfc(w: str) -> str:
    return unicodedata.normalize("NFC", w.strip())


def load_apple_counts() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    tsv = DATA / "gu_lexicon.tsv"
    if tsv.exists():
        for line in tsv.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            gu, _roman, w = parts[0], parts[1], int(parts[2])
            gu = nfc(gu)
            if is_gujarati_word(gu):
                counts[gu] = max(counts[gu], w)
    blob = ROOT / "rime" / "gu_lexicon_blob.json"
    if blob.exists():
        data = json.loads(blob.read_text(encoding="utf-8"))
        weights = data.get("weights") or {}
        lex = data.get("lexicon") or {}
        for roman, gu in lex.items():
            gu = nfc(str(gu))
            if not is_gujarati_word(gu):
                continue
            w = int(weights.get(roman, 100))
            counts[gu] = max(counts[gu], w)
    return dict(counts)


def fetch_text(url: str, cache: Path, min_size: int = 500) -> str:
    if cache.exists() and cache.stat().st_size >= min_size:
        return cache.read_text(encoding="utf-8", errors="ignore")
    print(f"fetch {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 re-gu-trans/2.7"})
        with urllib.request.urlopen(req, timeout=90) as resp:
            text = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        if cache.exists() and cache.stat().st_size > 0:
            print(f"WARN: fetch failed ({e}); using stale cache {cache}")
            return cache.read_text(encoding="utf-8", errors="ignore")
        raise SystemExit(f"Failed to fetch {url}: {e}\nPlace file at {cache} and re-run.") from e
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def load_google_counts() -> dict[str, int]:
    text = fetch_text(GOOGLE_URL, EXT / "gu_google_wordcounts.txt")
    counts: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.strip().split("\t")
        if len(parts) != 2:
            continue
        a, b = parts[0], parts[1]
        if a.isdigit() and is_gujarati_word(b):
            w = nfc(b)
            counts[w] = max(counts.get(w, 0), int(a))
        elif b.isdigit() and is_gujarati_word(a):
            w = nfc(a)
            counts[w] = max(counts.get(w, 0), int(b))
    return counts


def load_indic_counts() -> dict[str, int]:
    text = fetch_text(INDIC_URL, EXT / "gu_indic_wordfreq.txt")
    counts: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        word, raw = parts[0], parts[-1]
        if not raw.isdigit() or not is_gujarati_word(word):
            continue
        w = nfc(word)
        counts[w] = max(counts.get(w, 0), int(raw))
    return counts


def load_aspell_words() -> set[str]:
    """kartikm/gu-wordlist — base of Debian aspell-gu (GPL-2+)."""
    text = fetch_text(ASPELL_URL, EXT / "gu_aspell_wordlist.txt")
    out: set[str] = set()
    for line in text.splitlines():
        w = nfc(line)
        if not w or w.startswith("#"):
            continue
        # some lists are "word" or "word count"
        w = w.split()[0] if w.split() else w
        if is_gujarati_word(w):
            out.add(w)
    return out


def load_hunspell_words() -> set[str]:
    """Parse Hunspell .dic: first line = count; entries word or word/FLAGS."""
    text = fetch_text(HUNSPELL_URL, EXT / "gu_IN.dic")
    out: set[str] = set()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        raw = line.strip()
        if not raw:
            continue
        if i == 0 and raw.isdigit():
            continue
        if raw.startswith("#"):
            continue
        word = raw.split("/")[0].strip()
        word = nfc(word)
        if is_gujarati_word(word):
            out.add(word)
    return out


def build_stems(word_counts: dict[str, int]) -> dict[str, int]:
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
    EXT.mkdir(parents=True, exist_ok=True)

    apple = load_apple_counts()
    google = load_google_counts()
    indic = load_indic_counts()
    aspell = load_aspell_words()
    hunspell = load_hunspell_words()
    attested = aspell | hunspell

    print(
        f"apple={len(apple)} google={len(google)} indic={len(indic)} "
        f"aspell={len(aspell)} hunspell={len(hunspell)} attested_union={len(attested)}"
    )

    merged: dict[str, int] = {}
    for w, c in google.items():
        merged[w] = max(merged.get(w, 0), c)
    for w, c in indic.items():
        merged[w] = max(merged.get(w, 0), max(c // 10, 1))
    for w, c in apple.items():
        merged[w] = max(merged.get(w, 0), c * 2 if c >= 100 else max(c, 200))

    # Spell-dict floor: grammatically correct words always beat pure inventions
    for w in attested:
        merged[w] = max(merged.get(w, 0), ATTESTED_FLOOR)

    stems = build_stems(merged)
    lines = [f"{w}\t{c}" for w, c in sorted(merged.items(), key=lambda x: (-x[1], x[0]))]
    uni = OUT_DIR / "unigram.tsv"
    uni.write_text("\n".join(lines) + "\n", encoding="utf-8")

    stem_path = OUT_DIR / "stems.json"
    top_stems = dict(sorted(stems.items(), key=lambda x: -x[1])[:80000])
    stem_path.write_text(json.dumps(top_stems, ensure_ascii=False), encoding="utf-8")

    attested_path = OUT_DIR / "attested.json"
    attested_list = sorted(attested)
    attested_path.write_text(
        json.dumps({"words": attested_list, "floor": ATTESTED_FLOOR}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    (ROOT / "rime" / "lm").mkdir(exist_ok=True)
    (ROOT / "rime" / "lm" / "unigram.tsv").write_text(uni.read_text(encoding="utf-8"), encoding="utf-8")
    (ROOT / "rime" / "lm" / "stems.json").write_bytes(stem_path.read_bytes())
    (ROOT / "rime" / "lm" / "attested.json").write_bytes(attested_path.read_bytes())

    for probe in ["જમીન", "કેમ", "ફાવે", "ફાવશે", "ફાવો", "ગુજરાત", "કેટલી", "પોષતું"]:
        print(
            f"  {probe}: count={merged.get(probe, 0)} "
            f"attested={probe in attested} stem_ફાવ={stems.get('ફાવ', 0) if 'ફાવ' in probe or probe.startswith('ફ') else ''}"
        )

    print(f"stem ફાવ -> {stems.get('ફાવ', 0)}")
    print(
        f"wrote {uni} ({len(merged)} words), {stem_path} ({len(top_stems)} stems), "
        f"{attested_path} ({len(attested_list)} attested)"
    )


if __name__ == "__main__":
    main()
