#!/usr/bin/env python3
"""Build Gujarati native-script frequency + attested + unique-quality dataset.

Provenance tiers:
  T0  Apple      — blob/tsv + local Marisa/probe natives (strong floor + attested)
  T0b Google IME — local Input Tools extract (attested floor 80)
  T1  Spell/NLP  — aspell, hunspell, Dakshina, Indic-Glossaries (floor 50)
  T2  Wiki       — kartikm, wikidict, wipfli wiki/wikidata (floor 40)
  T3  Corpus     — Google wordcounts, Indic Keyboard, IndicCorp-v2 unigrams (freq)
  T4  Soft       — Aksharantar + AI4Bharat IndicXlit wordlist: unigram floor only (NOT attested)

Output:
  rime/js/lm/unigram.tsv, stems.json, attested.json  (single source of truth for qjs)
  data/quality/unique_gu_words.tsv, unique_gu_stats.json

Soft unigram prune: UNIGRAM_SOFT_MIN (default 100) drops Aksharantar-floor-only rows.
Attested compact: ATTESTED_COMPACT=1 (default) drops wipfli-only floor words.

Caches under data/external/ (gitignored). Never commit proprietary binaries.
"""
from __future__ import annotations

import io
import json
import os
import re
import tarfile
import unicodedata
import urllib.request
import zipfile
from collections import Counter, defaultdict
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
WIPFLI_WIKI_URL = "https://pub-726b01260c98468a9387cc0dfcb7386b.r2.dev/wikipedia-gujarati-corpus.txt.zip"
WIPFLI_WIKIDATA_URL = "https://pub-726b01260c98468a9387cc0dfcb7386b.r2.dev/wikidata-gujarati-corpus.txt.zip"
DAKSHINA_TAR_URL = "https://storage.googleapis.com/gresearch/dakshina/dakshina_dataset_v1.0.tar"
# AI4Bharat S3 often 403 from CI/home nets — place zips under data/external/ if blocked.
GLOSSARY_URLS = [
    "https://anuvaad-raw-datasets.s3-us-west-2.amazonaws.com/glossary-dataset-indoword.zip",
    "https://anuvaad-raw-datasets.s3-us-west-2.amazonaws.com/glossary-dataset-bharatvani.zip",
    "https://anuvaad-raw-datasets.s3-us-west-2.amazonaws.com/glossary-dataset-cstt.zip",
    "https://anuvaad-raw-datasets.s3-us-west-2.amazonaws.com/glossary-dataset-osf.zip",
]
INDICCORP_GU_URL = "https://huggingface.co/datasets/ai4bharat/IndicCorpV2/resolve/main/data/gu.txt"

FLOOR_SPELL = 60
FLOOR_WIKI = 45
FLOOR_AKSHA = 40
FLOOR_GOOGLE_IME = 90
# Soft (non-attested / Aksharantar-floor) unigram entries need real corpus mass.
# Provenance (frost/ice): IME/spell floors outrank soft Aksharantar pad.
UNIGRAM_SOFT_MIN = int(os.environ.get("UNIGRAM_SOFT_MIN", "100"))
# AI4Bharat IndicXlit vocab — soft unigram only; floor ≥ soft-min so rows survive prune
FLOOR_A4B = max(UNIGRAM_SOFT_MIN, int(os.environ.get("FLOOR_A4B", str(UNIGRAM_SOFT_MIN))))
# Drop wipfli-only floor words from attested (kartikm/wikidict + T0/T1 kept).
ATTESTED_COMPACT = os.environ.get("ATTESTED_COMPACT", "1") != "0"
INDICCORP_TOP_N = 500_000
INDICCORP_MAX_BYTES = int(os.environ.get("INDICCORP_MAX_BYTES", str(80 * 1024 * 1024)))

# Strong attested floors — always kept in unigram + attested.
HIGH_ATTESTED = frozenset(
    {"apple", "google_ime", "aspell", "hunspell", "dakshina", "glossaries"}
)
CURATED_WIKI = frozenset({"wiki_kartikm", "wiki_dict"})
WIPFLI_WIKI = frozenset({"wipfli_wiki", "wipfli_wikidata"})
CORPUS_SRC = frozenset({"google", "indic", "indiccorp"})

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
GU_TOKEN = re.compile(r"[\u0A80-\u0AFF]{2,}")


def is_gujarati_word(w: str) -> bool:
    return bool(w) and any("\u0A80" <= ch <= "\u0AFF" for ch in w)


def nfc(w: str) -> str:
    return unicodedata.normalize("NFC", w.strip())


def clean_wiki_token(raw: str) -> str | None:
    w = nfc(raw)
    if not w or w.startswith("#"):
        return None
    w = w.split("\t")[0].split()[0] if w.split() else w
    w = DISAMB.sub("", w).strip()
    w = w.strip(".,;:!?\"'`|/\\")
    if len(w) < 2 or not is_gujarati_word(w):
        return None
    latin = sum(1 for c in w if ("a" <= c <= "z") or ("A" <= c <= "Z"))
    if latin > len(w) // 2:
        return None
    return w


def fetch_bytes(url: str, cache: Path, min_size: int = 200) -> bytes:
    if cache.exists() and cache.stat().st_size >= min_size:
        return cache.read_bytes()
    print(f"fetch {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 re-gu-trans/2.9"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = resp.read()
    except Exception as e:
        if cache.exists() and cache.stat().st_size > 0:
            print(f"WARN: fetch failed ({e}); using stale cache {cache}")
            return cache.read_bytes()
        raise
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(data)
    return data


def fetch_text(url: str, cache: Path, min_size: int = 200) -> str:
    return fetch_bytes(url, cache, min_size).decode("utf-8", errors="ignore")


def load_native_list(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        w = nfc(line)
        if is_gujarati_word(w) and len(w) >= 2:
            out.add(w)
    return out


def load_apple_counts() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    tsv = DATA / "gu_lexicon.tsv"
    if tsv.exists():
        for line in tsv.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            gu, w = nfc(parts[0]), int(parts[2])
            if is_gujarati_word(gu):
                counts[gu] = max(counts[gu], w)
    blob = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
    if blob.exists():
        data = json.loads(blob.read_text(encoding="utf-8"))
        weights = data.get("weights") or {}
        for roman, gu in (data.get("lexicon") or {}).items():
            gu = nfc(str(gu))
            if not is_gujarati_word(gu):
                continue
            counts[gu] = max(counts[gu], int(weights.get(roman, 100)))
    # Extra proprietary Marisa/probe natives (weight-less → floor via merge)
    for w in load_native_list(EXT / "apple_native_words.txt"):
        counts[w] = max(counts[w], 200)
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
            counts[nfc(b)] = max(counts.get(nfc(b), 0), int(a))
        elif b.isdigit() and is_gujarati_word(a):
            counts[nfc(a)] = max(counts.get(nfc(a), 0), int(b))
    return counts


def load_indic_counts() -> dict[str, int]:
    text = fetch_text(INDIC_URL, EXT / "gu_indic_wordfreq.txt")
    counts: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) < 2 or not parts[-1].isdigit() or not is_gujarati_word(parts[0]):
            continue
        w = nfc(parts[0])
        counts[w] = max(counts.get(w, 0), int(parts[-1]))
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
    return load_native_list(EXT / "aksharantar_gu_native.txt")


def load_a4b_natives() -> set[str]:
    """AI4Bharat IndicXlit GU wordlist (filtered). Run scripts/ingest_a4b_gu_words.py first."""
    cache = EXT / "a4b_gu_natives.txt"
    if not cache.exists() or cache.stat().st_size < 100:
        # Auto-ingest from Downloads if present
        helper = ROOT / "scripts" / "ingest_a4b_gu_words.py"
        if helper.exists():
            try:
                import importlib.util

                spec = importlib.util.spec_from_file_location("ingest_a4b_gu_words", helper)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    mod.main()
            except Exception as e:
                print(f"WARN: a4b ingest helper: {e}")
    return load_native_list(cache)


def load_wipfli_words() -> tuple[set[str], set[str]]:
    """Return (wikipedia_set, wikidata_set)."""
    wiki: set[str] = set()
    wikidata: set[str] = set()
    for url, cache_name, bucket in (
        (WIPFLI_WIKI_URL, "wipfli_wikipedia_gu.zip", wiki),
        (WIPFLI_WIKIDATA_URL, "wipfli_wikidata_gu.zip", wikidata),
    ):
        try:
            data = fetch_bytes(url, EXT / cache_name, min_size=1000)
        except Exception as e:
            print(f"WARN: wipfli fetch failed ({e}); skip {cache_name}")
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for name in zf.namelist():
                    if name.endswith("/"):
                        continue
                    text = zf.read(name).decode("utf-8", errors="ignore")
                    for line in text.splitlines():
                        w = clean_wiki_token(line)
                        if w:
                            bucket.add(w)
        except Exception as e:
            print(f"WARN: wipfli parse {cache_name}: {e}")
    return wiki, wikidata


def load_dakshina_natives() -> set[str]:
    cache = EXT / "dakshina_gu_natives.txt"
    if cache.exists() and cache.stat().st_size > 100:
        return load_native_list(cache)

    tar_path = EXT / "dakshina_dataset_v1.0.tar"
    out: set[str] = set()
    if not tar_path.exists():
        if os.environ.get("FETCH_DAKSHINA") == "1":
            print("FETCH_DAKSHINA=1 — downloading ~2GB Dakshina tar (one-time)...")
            try:
                fetch_bytes(DAKSHINA_TAR_URL, tar_path, min_size=1_000_000)
            except Exception as e:
                print(f"WARN: Dakshina download failed ({e}); skip")
                return set()
        else:
            print(
                "WARN: Dakshina natives missing. Place data/external/dakshina_gu_natives.txt "
                "or dakshina_dataset_v1.0.tar (or FETCH_DAKSHINA=1). Skip."
            )
            return set()

    print(f"extract Dakshina GU lexicons from {tar_path}")
    try:
        with tarfile.open(tar_path, "r") as tf:
            for m in tf.getmembers():
                name = m.name.replace("\\", "/")
                if "/gu/" not in name and not name.startswith("gu/"):
                    continue
                if "lexicon" not in name.lower() and not name.endswith(".tsv"):
                    continue
                if not m.isfile():
                    continue
                f = tf.extractfile(m)
                if not f:
                    continue
                text = f.read().decode("utf-8", errors="ignore")
                for line in text.splitlines():
                    parts = line.split("\t")
                    # Dakshina lexicon: native \\t roman \\t ...
                    for cell in parts[:2]:
                        w = nfc(cell)
                        if is_gujarati_word(w) and len(w) >= 2:
                            out.add(w)
    except Exception as e:
        print(f"WARN: Dakshina extract failed ({e})")
        return set()

    cache.write_text("\n".join(sorted(out)) + "\n", encoding="utf-8")
    print(f"cached {cache} ({len(out)})")
    return out


def load_glossary_natives() -> set[str]:
    cache = EXT / "indic_glossary_gu_natives.txt"
    if cache.exists() and cache.stat().st_size > 100:
        return load_native_list(cache)

    out: set[str] = set()
    local_zips = sorted(EXT.glob("glossary-dataset-*.zip"))
    for path in local_zips:
        try:
            data = path.read_bytes()
            print(f"parse local glossary {path.name}")
        except Exception as e:
            print(f"WARN: glossary read {path}: {e}")
            continue
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for zn in zf.namelist():
                    if zn.endswith("/"):
                        continue
                    raw = zf.read(zn)
                    try:
                        text = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        try:
                            text = raw.decode("utf-16")
                        except Exception:
                            continue
                    for m in GU_TOKEN.finditer(text):
                        w = nfc(m.group(0))
                        if is_gujarati_word(w):
                            out.add(w)
        except Exception as e:
            print(f"WARN: glossary parse {path.name}: {e}")

    if not out and not local_zips:
        for url in GLOSSARY_URLS:
            name = url.rsplit("/", 1)[-1]
            try:
                data = fetch_bytes(url, EXT / name, min_size=1000)
            except Exception as e:
                print(f"WARN: glossary fetch {name}: {e}")
                continue
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for zn in zf.namelist():
                        if zn.endswith("/"):
                            continue
                        raw = zf.read(zn)
                        try:
                            text = raw.decode("utf-8")
                        except UnicodeDecodeError:
                            continue
                        for m in GU_TOKEN.finditer(text):
                            w = nfc(m.group(0))
                            if is_gujarati_word(w):
                                out.add(w)
            except Exception as e:
                print(f"WARN: glossary parse {name}: {e}")

    if out:
        cache.write_text("\n".join(sorted(out)) + "\n", encoding="utf-8")
        print(f"cached {cache} ({len(out)})")
    else:
        print(
            "WARN: no glossary GU natives. Place glossary-dataset-*.zip under data/external/ "
            "(S3 may 403 from CI)."
        )
    return out


def load_indiccorp_counts() -> dict[str, int]:
    """Stream/capped IndicCorp v2 gu.txt → top-N unigrams (cached TSV)."""
    cache = EXT / "gu_indiccorp_v2_unigrams.tsv"
    if cache.exists() and cache.stat().st_size > 1000:
        counts: dict[str, int] = {}
        for line in cache.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].isdigit() and is_gujarati_word(parts[0]):
                counts[nfc(parts[0])] = int(parts[1])
        return counts

    if os.environ.get("FETCH_INDICCORP") != "1" and not (EXT / "indiccorp_gu.txt").exists():
        print(
            "WARN: IndicCorp v2 unigrams missing. Place data/external/gu_indiccorp_v2_unigrams.tsv "
            "or set FETCH_INDICCORP=1 (streams up to INDICCORP_MAX_BYTES). Skip."
        )
        return {}

    src = EXT / "indiccorp_gu.txt"
    counter: Counter[str] = Counter()
    try:
        if src.exists():
            print(f"count IndicCorp from {src}")
            fh = src.open("r", encoding="utf-8", errors="ignore")
            streamed = False
        else:
            print(f"stream IndicCorp gu.txt (cap {INDICCORP_MAX_BYTES} bytes)...")
            req = urllib.request.Request(INDICCORP_GU_URL, headers={"User-Agent": "Mozilla/5.0 re-gu-trans/2.9"})
            resp = urllib.request.urlopen(req, timeout=120)
            fh = io.TextIOWrapper(resp, encoding="utf-8", errors="ignore")
            streamed = True
        read = 0
        for line in fh:
            read += len(line.encode("utf-8", errors="ignore"))
            for m in GU_TOKEN.finditer(line):
                w = nfc(m.group(0))
                if is_gujarati_word(w):
                    counter[w] += 1
            if streamed and read >= INDICCORP_MAX_BYTES:
                print(f"IndicCorp stream cap reached ({read} bytes)")
                break
        fh.close()
    except Exception as e:
        print(f"WARN: IndicCorp failed ({e}); skip")
        return {}

    top = counter.most_common(INDICCORP_TOP_N)
    lines = [f"{w}\t{c}" for w, c in top]
    cache.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"cached {cache} types={len(top)}")
    return dict(top)


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


def prune_unigram(
    merged: dict[str, int],
    attested: set[str],
    prov: dict[str, set[str]],
) -> dict[str, int]:
    """Drop soft-floor / pure wiki-floor unigram rows; keep strong attested + corpus mass."""
    out: dict[str, int] = {}
    dropped_soft = 0
    dropped_wiki_floor = 0
    for w, c in merged.items():
        sources = prov.get(w, set())
        if sources & HIGH_ATTESTED:
            out[w] = c
            continue
        if w in attested:
            # Wiki/other attested: keep unigram row only with above-floor evidence.
            if c > FLOOR_WIKI or sources & CORPUS_SRC:
                out[w] = c
            else:
                dropped_wiki_floor += 1
            continue
        if c >= UNIGRAM_SOFT_MIN:
            out[w] = c
        else:
            dropped_soft += 1
    print(
        f"unigram prune: {len(merged)} → {len(out)} "
        f"(soft_min={UNIGRAM_SOFT_MIN} dropped_soft={dropped_soft} "
        f"dropped_wiki_floor={dropped_wiki_floor})"
    )
    return out


def compact_attested(attested: set[str], prov: dict[str, set[str]], merged: dict[str, int]) -> set[str]:
    """Keep T0/T1 + curated wiki; drop wipfli-only floor words when ATTESTED_COMPACT=1."""
    if not ATTESTED_COMPACT:
        return attested
    out: set[str] = set()
    dropped = 0
    for w in attested:
        sources = prov.get(w, set())
        if sources & HIGH_ATTESTED or sources & CURATED_WIKI:
            out.add(w)
            continue
        if sources & WIPFLI_WIKI:
            # Keep wipfli when also seen in corpus / curated / high tiers.
            if sources & (HIGH_ATTESTED | CURATED_WIKI | CORPUS_SRC) or merged.get(w, 0) > FLOOR_WIKI:
                out.add(w)
            else:
                dropped += 1
            continue
        out.add(w)
    print(f"attested compact: {len(attested)} → {len(out)} (dropped_wipfli_floor={dropped})")
    return out


def best_tier(sources: set[str]) -> str:
    order = [
        "apple",
        "google_ime",
        "aspell",
        "hunspell",
        "dakshina",
        "glossaries",
        "wiki_kartikm",
        "wiki_dict",
        "wipfli_wiki",
        "wipfli_wikidata",
        "google",
        "indic",
        "indiccorp",
        "aksharantar",
        "a4b",
    ]
    for s in order:
        if s not in sources:
            continue
        if s == "apple":
            return "T0"
        if s == "google_ime":
            return "T0b"
        if s in ("aspell", "hunspell", "dakshina", "glossaries"):
            return "T1"
        if s in ("wiki_kartikm", "wiki_dict", "wipfli_wiki", "wipfli_wikidata"):
            return "T2"
        if s in ("google", "indic", "indiccorp"):
            return "T3"
        if s == "aksharantar" or s == "a4b":
            return "T4"
    return "T3"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EXT.mkdir(parents=True, exist_ok=True)
    QUALITY.mkdir(parents=True, exist_ok=True)

    # Ensure proprietary extracts exist when local assets are present
    prop = ROOT / "scripts" / "extract_proprietary_gu_natives.py"
    if prop.exists():
        import importlib.util

        try:
            spec = importlib.util.spec_from_file_location("extract_proprietary_gu_natives", prop)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.main()
        except Exception as e:
            print(f"WARN: proprietary extract helper: {e}")

    apple = load_apple_counts()
    apple_set = set(apple) | load_native_list(EXT / "apple_native_words.txt")
    google_ime = load_native_list(EXT / "google_ime_native_words.txt")
    google = load_google_counts()
    indic = load_indic_counts()
    aspell = load_word_set(ASPELL_URL, EXT / "gu_aspell_wordlist.txt")
    hunspell = load_hunspell_words()
    wiki_k = load_word_set(WIKI_KARTIKM_URL, EXT / "gu_wikipedia_kartikm.txt", cleaner=clean_wiki_token)
    wiki_d = load_word_set(WIKI_DICT_URL, EXT / "gu_wikipedia_wikidict.txt", cleaner=clean_wiki_token)
    wipfli_w, wipfli_wd = load_wipfli_words()
    dakshina = load_dakshina_natives()
    glossaries = load_glossary_natives()
    indiccorp = load_indiccorp_counts()
    aksha = load_aksharantar_natives()
    a4b = load_a4b_natives()

    wiki = wiki_k | wiki_d | wipfli_w | wipfli_wd
    spell = aspell | hunspell
    # Attested: quality floors — exclude Aksharantar / A4B soft vocab (T4 unigram only)
    attested_full = apple_set | google_ime | spell | wiki | dakshina | glossaries

    print(
        f"apple={len(apple_set)} google_ime={len(google_ime)} "
        f"aspell={len(aspell)} hunspell={len(hunspell)} "
        f"dakshina={len(dakshina)} glossaries={len(glossaries)} "
        f"wiki_kartikm={len(wiki_k)} wiki_dict={len(wiki_d)} "
        f"wipfli_wiki={len(wipfli_w)} wipfli_wikidata={len(wipfli_wd)} "
        f"google={len(google)} indic={len(indic)} indiccorp={len(indiccorp)} "
        f"aksharantar={len(aksha)} a4b={len(a4b)} attested_full={len(attested_full)}"
    )

    prov: dict[str, set[str]] = defaultdict(set)
    for w in apple_set:
        prov[w].add("apple")
    for w in google_ime:
        prov[w].add("google_ime")
    for w in aspell:
        prov[w].add("aspell")
    for w in hunspell:
        prov[w].add("hunspell")
    for w in dakshina:
        prov[w].add("dakshina")
    for w in glossaries:
        prov[w].add("glossaries")
    for w in wiki_k:
        prov[w].add("wiki_kartikm")
    for w in wiki_d:
        prov[w].add("wiki_dict")
    for w in wipfli_w:
        prov[w].add("wipfli_wiki")
    for w in wipfli_wd:
        prov[w].add("wipfli_wikidata")
    for w in google:
        prov[w].add("google")
    for w in indic:
        prov[w].add("indic")
    for w in indiccorp:
        prov[w].add("indiccorp")
    for w in aksha:
        prov[w].add("aksharantar")
    for w in a4b:
        prov[w].add("a4b")

    merged: dict[str, int] = {}
    for w, c in google.items():
        merged[w] = max(merged.get(w, 0), c)
    for w, c in indic.items():
        merged[w] = max(merged.get(w, 0), max(c // 10, 1))
    for w, c in indiccorp.items():
        merged[w] = max(merged.get(w, 0), c)
    for w, c in apple.items():
        merged[w] = max(merged.get(w, 0), c * 2 if c >= 100 else max(c, 200))
    for w in apple_set:
        merged[w] = max(merged.get(w, 0), 200)
    for w in google_ime:
        merged[w] = max(merged.get(w, 0), FLOOR_GOOGLE_IME)
    for w in spell | dakshina | glossaries:
        merged[w] = max(merged.get(w, 0), FLOOR_SPELL)
    for w in wiki:
        merged[w] = max(merged.get(w, 0), FLOOR_WIKI)
    for w in aksha:
        merged[w] = max(merged.get(w, 0), FLOOR_AKSHA)
    for w in a4b:
        merged[w] = max(merged.get(w, 0), FLOOR_A4B)

    attested = compact_attested(attested_full, prov, merged)
    merged = prune_unigram(merged, attested, prov)

    uniq_lines = []
    wiki_only = 0
    for w in sorted(prov.keys()):
        sources = sorted(prov[w])
        tier = best_tier(prov[w])
        uniq_lines.append(f"{w}\t{tier}\t{','.join(sources)}")
        if prov[w] <= {"wiki_kartikm", "wiki_dict", "wipfli_wiki", "wipfli_wikidata"}:
            wiki_only += 1
    uniq_path = QUALITY / "unique_gu_words.tsv"
    uniq_path.write_text("\n".join(uniq_lines) + "\n", encoding="utf-8")

    stats = {
        "union": len(prov),
        "wiki_only": wiki_only,
        "wiki_union": len(wiki),
        "sources": {
            "apple": len(apple_set),
            "google_ime": len(google_ime),
            "aspell": len(aspell),
            "hunspell": len(hunspell),
            "dakshina": len(dakshina),
            "glossaries": len(glossaries),
            "wiki_kartikm": len(wiki_k),
            "wiki_dict": len(wiki_d),
            "wipfli_wiki": len(wipfli_w),
            "wipfli_wikidata": len(wipfli_wd),
            "google": len(google),
            "indic": len(indic),
            "indiccorp": len(indiccorp),
            "aksharantar": len(aksha),
            "a4b": len(a4b),
        },
        "floors": {
            "spell": FLOOR_SPELL,
            "wiki": FLOOR_WIKI,
            "aksharantar": FLOOR_AKSHA,
            "a4b": FLOOR_A4B,
            "google_ime": FLOOR_GOOGLE_IME,
            "unigram_soft_min": UNIGRAM_SOFT_MIN,
        },
        "unigram": len(merged),
        "attested_full": len(attested_full),
        "attested": len(attested),
        "attested_compact": ATTESTED_COMPACT,
        "attested_excludes_aksharantar": True,
    }
    stats_path = QUALITY / "unique_gu_stats.json"
    stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"unique quality union={stats['union']} wiki_only={wiki_only} attested={len(attested)} -> {uniq_path}")

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

    # Single source of truth for qjs: rime/js/lm/ (do not dual-write rime/lm/)
    legacy_lm = ROOT / "rime" / "lm"
    if legacy_lm.exists():
        print(f"NOTE: remove obsolete duplicate {legacy_lm} (qjs reads js/lm/)")

    for probe in ["જમીન", "કેમ", "ફાવે", "ફાવશે", "ગુજરાત", "કેટલી", "પરખાવ્યું"]:
        print(f"  {probe}: count={merged.get(probe, 0)} attested={probe in attested}")

    print(
        f"wrote {uni} ({len(merged)}), {stem_path} ({len(top_stems)}), "
        f"{attested_path} ({len(attested_list)}), {stats_path}"
    )


if __name__ == "__main__":
    main()
