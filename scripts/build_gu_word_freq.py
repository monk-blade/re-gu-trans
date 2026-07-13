#!/usr/bin/env python3
"""Build Gujarati native-script frequency + attested + unique-quality dataset.

Provenance tiers:
  T0 Apple   — lexicon natives (strong floor)
  T1 Spell   — aspell-gu + hunspell (floor 50)
  T2 Wiki    — kartikm wikipedia-wordlist + open-dict-data wikidict (floor 40)
  T3 Corpus  — Google wordcounts + Indic Keyboard (frequency)
  T4 Soft    — Aksharantar natives if cached (floor 50)

Output:
  rime/js/lm/unigram.tsv
  rime/js/lm/stems.json
  rime/js/lm/attested.json
  data/quality/unique_gu_words.tsv   — word\\ttier\\tsources
  data/quality/unique_gu_stats.json

Caches under data/external/ (gitignored).
"""
from __future__ import annotations

import json
import re
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "rime" / "js" / "lm"
DATA = ROOT / "data"
EXT = DATA / "external"
QUALITY = DATA / "quality"

GOOGLE_URL = "http://www.gstatic.com/i18n/corpora/wordcounts/gu.txt"
INDIC_URL = "https://raw.githubusercontent.com/jishnu7/dictionaries/master/languages/gu/wordfreq.txt"
ASPELL_URL = "https://raw.githubusercontent.com/kartikm/gu-wordlist/master/gu-wordlist.txt"
HUNSPELL_URL = "https://raw.githubusercontent.com/elastic/hunspell/master/dicts/gu_IN/gu_IN.dic"
WIKI_KARTIKM_URL = "https://raw.githubusercontent.com/kartikm/gu-wordlist/master/wikipedia-wordlist.txt"
WIKI_DICT_URL = "https://raw.githubusercontent.com/open-dict-data/wikidict-wordlist/master/data/gu-wordlist_wiki.txt"

FLOOR_SPELL = 50
FLOOR_WIKI = 40
FLOOR_AKSHA = 50

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

DISAMB = re.compile(r"\s*\([^)]*\)\s*")


def is_gujarati_word(w: str) -> bool:
    return bool(w) and any("\u0A80" <= ch <= "\u0AFF" for ch in w)


def nfc(w: str) -> str:
    return unicodedata.normalize("NFC", w.strip())


def clean_wiki_token(raw: str) -> str | None:
    """Normalize wiki title-like tokens to a Gujarati lemma."""
    w = nfc(raw)
    if not w or w.startswith("#"):
        return None
    w = w.split("\t")[0].split()[0] if w.split() else w
    w = DISAMB.sub("", w).strip()
    w = w.strip(".,;:!?\"'`|/\\")
    if len(w) < 2:
        return None
    if not is_gujarati_word(w):
        return None
    # drop mostly-latin mixed noise
    latin = sum(1 for c in w if ("a" <= c <= "z") or ("A" <= c <= "Z"))
    if latin > len(w) // 2:
        return None
    return w


def fetch_text(url: str, cache: Path, min_size: int = 200) -> str:
    if cache.exists() and cache.stat().st_size >= min_size:
        return cache.read_text(encoding="utf-8", errors="ignore")
    print(f"fetch {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 re-gu-trans/2.8"})
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


def load_word_set(url: str, cache: Path, cleaner=None) -> set[str]:
    text = fetch_text(url, cache)
    out: set[str] = set()
    for line in text.splitlines():
        if cleaner:
            w = cleaner(line)
        else:
            w = nfc(line)
            if not w or w.startswith("#"):
                continue
            w = w.split()[0] if w.split() else w
            if not is_gujarati_word(w):
                continue
        if w:
            out.add(w)
    return out


def load_hunspell_words() -> set[str]:
    text = fetch_text(HUNSPELL_URL, EXT / "gu_IN.dic")
    out: set[str] = set()
    for i, line in enumerate(text.splitlines()):
        raw = line.strip()
        if not raw or (i == 0 and raw.isdigit()) or raw.startswith("#"):
            continue
        word = nfc(raw.split("/")[0].strip())
        if is_gujarati_word(word):
            out.add(word)
    return out


def load_aksharantar_natives() -> set[str]:
    path = EXT / "aksharantar_gu_native.txt"
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        w = nfc(line)
        if is_gujarati_word(w):
            out.add(w)
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


def best_tier(sources: set[str]) -> str:
    order = ["apple", "aspell", "hunspell", "wiki_kartikm", "wiki_dict", "aksharantar", "google", "indic"]
    for s in order:
        if s in sources:
            if s == "apple":
                return "T0"
            if s in ("aspell", "hunspell"):
                return "T1"
            if s in ("wiki_kartikm", "wiki_dict"):
                return "T2"
            if s in ("google", "indic"):
                return "T3"
            if s == "aksharantar":
                return "T4"
    return "T3"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EXT.mkdir(parents=True, exist_ok=True)
    QUALITY.mkdir(parents=True, exist_ok=True)

    apple = load_apple_counts()
    google = load_google_counts()
    indic = load_indic_counts()
    aspell = load_word_set(ASPELL_URL, EXT / "gu_aspell_wordlist.txt")
    hunspell = load_hunspell_words()
    wiki_k = load_word_set(WIKI_KARTIKM_URL, EXT / "gu_wikipedia_kartikm.txt", cleaner=clean_wiki_token)
    wiki_d = load_word_set(WIKI_DICT_URL, EXT / "gu_wikipedia_wikidict.txt", cleaner=clean_wiki_token)
    aksha = load_aksharantar_natives()

    wiki = wiki_k | wiki_d
    spell = aspell | hunspell
    attested = spell | wiki | aksha

    print(
        f"apple={len(apple)} google={len(google)} indic={len(indic)} "
        f"aspell={len(aspell)} hunspell={len(hunspell)} "
        f"wiki_kartikm={len(wiki_k)} wiki_dict={len(wiki_d)} wiki_union={len(wiki)} "
        f"aksharantar={len(aksha)} attested={len(attested)}"
    )

    # Provenance map for unique-quality TSV
    prov: dict[str, set[str]] = defaultdict(set)
    for w in apple:
        prov[w].add("apple")
    for w in aspell:
        prov[w].add("aspell")
    for w in hunspell:
        prov[w].add("hunspell")
    for w in wiki_k:
        prov[w].add("wiki_kartikm")
    for w in wiki_d:
        prov[w].add("wiki_dict")
    for w in aksha:
        prov[w].add("aksharantar")
    for w in google:
        prov[w].add("google")
    for w in indic:
        prov[w].add("indic")

    merged: dict[str, int] = {}
    for w, c in google.items():
        merged[w] = max(merged.get(w, 0), c)
    for w, c in indic.items():
        merged[w] = max(merged.get(w, 0), max(c // 10, 1))
    for w, c in apple.items():
        merged[w] = max(merged.get(w, 0), c * 2 if c >= 100 else max(c, 200))
    for w in spell:
        merged[w] = max(merged.get(w, 0), FLOOR_SPELL)
    for w in wiki:
        merged[w] = max(merged.get(w, 0), FLOOR_WIKI)
    for w in aksha:
        merged[w] = max(merged.get(w, 0), FLOOR_AKSHA)

    # Unique quality artifact
    uniq_lines = []
    wiki_only = 0
    for w in sorted(prov.keys()):
        sources = sorted(prov[w])
        tier = best_tier(prov[w])
        uniq_lines.append(f"{w}\t{tier}\t{','.join(sources)}")
        if prov[w] <= {"wiki_kartikm", "wiki_dict"}:
            wiki_only += 1
    uniq_path = QUALITY / "unique_gu_words.tsv"
    uniq_path.write_text("\n".join(uniq_lines) + "\n", encoding="utf-8")

    stats = {
        "union": len(prov),
        "wiki_only": wiki_only,
        "wiki_union": len(wiki),
        "sources": {
            "apple": len(apple),
            "aspell": len(aspell),
            "hunspell": len(hunspell),
            "wiki_kartikm": len(wiki_k),
            "wiki_dict": len(wiki_d),
            "google": len(google),
            "indic": len(indic),
            "aksharantar": len(aksha),
        },
        "floors": {"spell": FLOOR_SPELL, "wiki": FLOOR_WIKI, "aksharantar": FLOOR_AKSHA},
        "unigram": len(merged),
        "attested": len(attested),
    }
    stats_path = QUALITY / "unique_gu_stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"unique quality union={stats['union']} wiki_only={wiki_only} -> {uniq_path}")

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
        json.dumps({"words": attested_list, "floor": FLOOR_SPELL}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    (ROOT / "rime" / "lm").mkdir(exist_ok=True)
    (ROOT / "rime" / "lm" / "unigram.tsv").write_text(uni.read_text(encoding="utf-8"), encoding="utf-8")
    (ROOT / "rime" / "lm" / "stems.json").write_bytes(stem_path.read_bytes())
    (ROOT / "rime" / "lm" / "attested.json").write_bytes(attested_path.read_bytes())

    for probe in ["જમીન", "કેમ", "ફાવે", "ફાવશે", "ગુજરાત", "કેટલી"]:
        print(f"  {probe}: count={merged.get(probe, 0)} attested={probe in attested}")

    print(f"stem ફાવ -> {stems.get('ફાવ', 0)}")
    print(
        f"wrote {uni} ({len(merged)}), {stem_path} ({len(top_stems)}), "
        f"{attested_path} ({len(attested_list)}), {stats_path}"
    )


if __name__ == "__main__":
    main()
