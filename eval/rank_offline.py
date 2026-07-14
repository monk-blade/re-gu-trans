#!/usr/bin/env python3
"""Offline ranking eval mirroring gujarati_translator.js policy (v2.8).

Loads lexicon blob + unigram + stems + attested. Checks smoke top-1 and a
small OOV/fuzzy sample. Does not require Rime/Squirrel.
"""
from __future__ import annotations

import json
import math
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOB = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
BLOB_LEGACY = ROOT / "rime" / "gu_lexicon_blob.json"
UNI = ROOT / "rime" / "js" / "lm" / "unigram.tsv"
STEMS = ROOT / "rime" / "js" / "lm" / "stems.json"
ATTESTED = ROOT / "rime" / "js" / "lm" / "attested.json"
OUT = ROOT / "eval" / "rank_results.json"

TIER_EXACT, TIER_DICT, TIER_PHONETIC, TIER_LATIN, TIER_PREFIX = 0, 1, 2, 3, 4

CONFUSION_MAP = {
    "ch": ["chh"],
    "chh": ["ch"],
    "t": ["T"],
    "T": ["t"],
    "d": ["D"],
    "D": ["d"],
    "s": ["sh", "Sh"],
    "sh": ["Sh", "s"],
    "Sh": ["sh", "s"],
    "n": ["N"],
    "N": ["n"],
    "l": ["L"],
    "L": ["l"],
    "f": ["ph"],
    "ph": ["f"],
    "v": ["w"],
    "w": ["v"],
    "z": ["j"],
    "j": ["z"],
    "gn": ["gy", "gny", "jny"],
    "gy": ["gn", "gny", "jny"],
    "gny": ["gy", "gn", "jny"],
    "jny": ["gy", "gn", "gny"],
}
ENDING_VARIANTS = {
    "i": ["ii", "ee"],
    "ii": ["i"],
    "ee": ["i", "ii"],
    "u": ["uu", "un", "um"],
    "uu": ["u"],
    "un": ["u", "um"],
    "um": ["u", "un"],
    "a": ["aa"],
    "aa": ["a"],
}


def is_diphthong_i(s: str, i_pos: int) -> bool:
    """True when roman i/ii/ee at i_pos is the second half of ai/oi/ui/ei."""
    if not s or i_pos <= 0:
        return False
    return s[i_pos - 1] in ("a", "e", "o", "u")
GU_SUFFIXES = [
    "વાળાઓ", "વાળીઓ", "વાળું", "વાળી", "વાળા", "વાળો",
    "ીઓ", "ાઓ", "ોને", "ાને", "ીને", "ુંને",
    "માંથી", "માં", "થી", "ની", "નો", "ના", "ને", "નું", "નાં",
    "શે", "શો", "શું", "ીશ", "ીશું",
    "્યો", "્યા", "્યું",
    "તો", "તા", "તી", "તું", "તાં",
    "વું", "વા", "વાનું", "વાની", "વાના",
    "ે", "ો", "ા", "ી", "ું", "ાં",
]
MAX_ALT = 96

# Compact phonetic (same scheme as translator; longest-token greedy)
VIRAMA = "\u0ACD"
CONS = {
    "ksh": "ક્ષ", "x": "ક્ષ", "gy": "જ્ઞ", "gn": "જ્ઞ", "gny": "જ્ઞ", "jny": "જ્ઞ",
    "shr": "શ્ર", "tr": "ત્ર", "sth": "સ્થ", "str": "સ્ત્ર", "om": "ૐ",
    "chh": "છ", "ch": "ચ", "c": "ચ",
    "kh": "ખ", "k": "ક", "gh": "ઘ", "g": "ગ", "ng": "ઙ",
    "jh": "ઝ", "j": "જ", "ny": "ઞ", "Th": "ઠ", "T": "ટ", "Dh": "ઢ", "D": "ડ", "N": "ણ",
    "th": "થ", "t": "ત", "dh": "ધ", "d": "દ", "n": "ન",
    "ph": "ફ", "f": "ફ", "p": "પ", "bh": "ભ", "b": "બ", "m": "મ",
    "y": "ય", "r": "ર", "L": "ળ", "l": "લ", "v": "વ", "w": "વ",
    "sh": "શ", "Sh": "ષ", "s": "સ", "h": "હ", "z": "ઝ",
}
DIGITS = {str(i): "૦૧૨૩૪૫૬૭૮૯"[i] for i in range(10)}
VOW_IND = {
    "aa": "આ", "ii": "ઈ", "ee": "ઈ", "uu": "ઊ", "oo": "ઊ", "ai": "ઐ", "au": "ઔ",
    "a": "અ", "i": "ઇ", "u": "ઉ", "e": "એ", "o": "ઓ",
    "M": "ં", "H": "ઃ",
}
VOW_MAT = {
    "aa": "ા", "ii": "ી", "ee": "ી", "uu": "ૂ", "oo": "ૂ", "ai": "ૈ", "au": "ૌ",
    "i": "િ", "u": "ુ", "e": "ે", "o": "ો",
    "M": "ં", "H": "ઃ",
    # short a = inherent
}

SMOKE = [
    ("jamin", "જમીન"),
    ("favshe", "ફાવશે"),
    ("poshatu", "પોષતું"),
    ("ketli", "કેટલી"),
    ("mne", "મને"),
    ("parkhavyu", "પરખાવ્યું"),
    ("gai", "ગઈ"),
    # Pattern-family guards (Apple-like; rules must stay general)
    ("kyare", "ક્યારે"),  # a→aa lengthening must not demote strict exact
    ("joi", "જોઈ"),  # oi diphthong split
    ("avo", "આવો"),  # leading a↔aa
    ("wikas", "વિકાસ"),  # v↔w + aa
    ("hoi", "હોઈ"),  # oi family
    ("kui", "કુઈ"),  # ui diphthong
    ("zindabad", "ઝિંદાબાદ"),  # anusvara + long-a
    ("himmat", "હિમ્મત"),  # geminate
    ("swagat", "સ્વાગત"),  # mid a→aa over soft lex
    ("shah", "શાહ"),  # typed sh
    ("banda", "બાંદા"),  # soft-lex demotion
    ("mi", "મી"),  # short CV: near-exact +n must not steal over મી/મિ
    ("n", "ન"),  # IAST dental; ણ stays in menu via place twin
    # Design-doc orthography pack
    ("nahya", "નાહ્યા"),
    ("kirtan", "કીર્તન"),
    ("namaste", "નમસ્તે"),
    ("gujarat", "ગુજરાત"),
    ("shanti", "શાંતિ"),
    ("shaanti", "શાંતિ"),
    ("kshama", "ક્ષમા"),
    ("gnan", "જ્ઞાન"),
    ("gyaan", "જ્ઞાન"),
    ("swaagat", "સ્વાગત"),
    ("vidyaa", "વિદ્યા"),
    ("bhaasha", "ભાષા"),
    ("dukh", "દુઃખ"),
    ("ank", "અંક"),
    ("ghar", "ઘર"),
    ("gharma", "ઘરમાં"),
    ("a", "અ"),
    ("aa", "આ"),
    ("kh", "ખ"),
    ("2026", "૨૦૨૬"),
    ("vinash", "વિનાશ"),  # sh→s fuzzy must not steal over soft typed lex
    ("shabdo", "શબ્દો"),  # lexicon stem shabd + matra ો
    ("moolya", "મૂલ્ય"),
    ("mulya", "મૂલ્ય"),  # u↔oo mid-vowel
    ("moolyama", "મૂલ્યમાં"),  # stem + માં postfix
    ("mulyama", "મૂલ્યમાં"),
    ("aachar", "આચાર"),  # bare stem over આચારાંગ morph
    ("aad", "આડ"),  # bare over near-exact આડું
]


def load_blob() -> dict:
    path = BLOB if BLOB.exists() else BLOB_LEGACY
    return json.loads(path.read_text(encoding="utf-8"))


def load_unigram() -> dict[str, int]:
    m: dict[str, int] = {}
    for line in UNI.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        m[unicodedata.normalize("NFC", parts[0])] = int(parts[1])
    return m


def load_stems() -> dict[str, int]:
    return {k: int(v) for k, v in json.loads(STEMS.read_text(encoding="utf-8")).items()}


def load_attested() -> tuple[set[str], int]:
    data = json.loads(ATTESTED.read_text(encoding="utf-8"))
    return set(data.get("words") or []), int(data.get("floor") or 50)


def with_ending(s: str) -> set[str]:
    out = {s}
    for frm, tos in ENDING_VARIANTS.items():
        if s.endswith(frm) and len(s) > len(frm):
            if frm in ("i", "ii", "ee") and is_diphthong_i(s, len(s) - len(frm)):
                continue
            stem = s[: -len(frm)]
            for to in tos:
                out.add(stem + to)
    return out


def with_mid_vowel(s: str) -> set[str]:
    out = {s}
    if len(s) < 3:
        return out
    pairs = [
        ("i", "ii"),
        ("ii", "i"),
        ("a", "aa"),
        ("aa", "a"),
        ("oo", "u"),
        ("u", "oo"),
        ("uu", "oo"),
        ("oo", "uu"),
    ]
    for frm, to in pairs:
        idx, added = 0, 0
        while idx <= len(s) - len(frm) and added < 4:
            at = s.find(frm, idx)
            if at < 0:
                break
            if at > 0:
                if frm in ("i", "ii") and is_diphthong_i(s, at):
                    idx = at + 1
                    continue
                if frm == "u" and s[at - 1] in ("o", "a"):
                    idx = at + 1
                    continue
                out.add(s[:at] + to + s[at + len(frm) :])
                added += 1
            idx = at + 1
    return out


def with_leading_vowel(s: str) -> set[str]:
    out = {s}
    if not s or len(s) < 2:
        return out
    if s.startswith("aa"):
        out.add("a" + s[2:])
    elif s.startswith("a") and s[1] != "a":
        out.add("aa" + s[1:])
    return out


def with_retroflex_nasal(s: str) -> set[str]:
    out = {s}
    if not s or len(s) < 2:
        return out
    for stem in ("Th", "Dh", "T", "D"):
        idx = 0
        while idx <= len(s) - len(stem) - 1:
            at = s.find(stem, idx)
            if at < 0:
                break
            n_pos = at + len(stem)
            if n_pos < len(s) and s[n_pos] == "n":
                out.add(s[:n_pos] + "N" + s[n_pos + 1 :])
            idx = at + 1
    return out


def apply_confusions(s: str) -> set[str]:
    out = {s}
    keys = sorted(CONFUSION_MAP.keys(), key=len, reverse=True)
    for frm in keys:
        for to in CONFUSION_MAP[frm]:
            idx = 0
            while idx <= len(s) - len(frm):
                at = s.find(frm, idx)
                if at < 0:
                    break
                out.add(s[:at] + to + s[at + len(frm) :])
                idx = at + 1
    return out


CONS_CHARS = set("kKgGcCjJTDdNtnNpPbBmMyrRlLvVwWshHzf")  # rough; use CONS keys


def insert_a_between_cons(s: str) -> set[str]:
    """Mirror JS: insert 'a' between adjacent consonant tokens."""
    out = {s}
    # character-level: if two CONS singles abut, insert a
    i = 0
    keys = sorted(CONS.keys(), key=len, reverse=True)
    # tokenize into cons/other roughly
    parts: list[tuple[str, str]] = []
    while i < len(s):
        matched = None
        for t in keys:
            if s.startswith(t, i):
                matched = t
                break
        if matched:
            parts.append(("c", matched))
            i += len(matched)
        else:
            parts.append(("o", s[i]))
            i += 1
    for idx in range(len(parts) - 1):
        if parts[idx][0] == "c" and parts[idx + 1][0] == "c":
            left = "".join(p for _, p in parts[: idx + 1])
            right = "".join(p for _, p in parts[idx + 1 :])
            out.add(left + "a" + right)
    return out


def with_trailing_schwa(s: str) -> set[str]:
    out = {s}
    if not s or len(s) < 3:
        return out
    # rough: last char is a consonant letter used in CONS singles
    last = s[-1]
    if last in "kKgGcCjJTDdNtnNpPbBmMyrRlLvVwWshHzf" or last in CONS:
        out.add(s + "a")
    return out


# Stops that take homorganic / simplified anusvara (ISO 15919 / ITRANS M)
_ANUSVARA_STOPS = (
    "kh", "gh", "chh", "ch", "jh", "Th", "th", "Dh", "dh", "ph", "bh",
    "k", "g", "c", "j", "T", "t", "D", "d", "p", "b",
)

# Enable English loan digraph alts (gated; turn off if smoke regressions).
ENABLE_LOAN_DIGRAPHS = True


def with_anusvara_nasals(s: str) -> set[str]:
    """n/m before stop → M (ં) alternate — zindabad→ziMdabad→ઝિં…"""
    out = {s}
    if not s:
        return out
    for nasal in ("n", "m"):
        idx = 0
        while idx < len(s):
            at = s.find(nasal, idx)
            if at < 0:
                break
            rest = s[at + 1 :]
            for stop in _ANUSVARA_STOPS:
                if rest.startswith(stop):
                    out.add(s[:at] + "M" + rest)
                    break
            idx = at + 1
    return out


def with_geminates(s: str) -> set[str]:
    """mm/nn/… → m+m (explicit virama) for હિમ્મત-style geminates."""
    out = {s}
    if not s or len(s) < 2:
        return out
    for d in ("mm", "nn", "tt", "kk", "ll", "pp", "bb", "dd", "gg", "jj", "ss"):
        idx = 0
        while idx <= len(s) - 2:
            at = s.find(d, idx)
            if at < 0:
                break
            out.add(s[:at] + d[0] + "+" + d[1] + s[at + 2 :])
            idx = at + 1
    return out


def with_loan_digraphs(s: str) -> set[str]:
    """Bounded English-loan roman rewrites (Surana / Aksharantar NEF style)."""
    out = {s}
    if not ENABLE_LOAN_DIGRAPHS or not s:
        return out
    lower = s.lower()
    # Only rewrite clearly Latin-looking tokens (avoid mane→man, kyare→kayar).
    loanish = bool(
        re.search(r"(sch|tion|qu|ck|oo|ee|school|college|doctor|hospital|london)", lower)
    )
    if not loanish:
        return out
    reps = [
        ("sch", "sk"),
        ("tion", "shan"),
        ("qu", "kv"),
        ("ck", "k"),
        ("oo", "uu"),
        ("ee", "ii"),
    ]
    for a, b in reps:
        idx = 0
        while idx <= len(lower) - len(a):
            at = lower.find(a, idx)
            if at < 0:
                break
            out.add(lower[:at] + b + lower[at + len(a) :])
            idx = at + 1
    if len(lower) >= 5 and lower.endswith("e") and lower[-2] in "bcdfghjklmnpqrstvwxyz":
        out.add(lower[:-1])
    return out


def with_double_aa(s: str) -> set[str]:
    """Up to two interior a→aa (ziMdabad → ziMdaabaad)."""
    out = {s}
    for one in with_mid_vowel(s):
        out.add(one)
        out |= with_mid_vowel(one)
    return out


def expand_roman(input_s: str) -> set[str]:
    lower = input_s.lower()
    forms = {lower, input_s}
    seed = set(with_ending(lower)) | set(with_mid_vowel(lower)) | apply_confusions(lower)
    seed |= with_leading_vowel(lower)
    seed |= with_trailing_schwa(lower)
    seed |= with_retroflex_nasal(lower)
    seed |= with_anusvara_nasals(lower)
    seed |= with_geminates(lower)
    seed |= with_loan_digraphs(lower)
    seed |= with_visarga_h(lower)
    # Prioritize anusvara × double-aa before MAX_ALT fills with junk
    for nas in list(with_anusvara_nasals(lower)):
        seed |= with_double_aa(nas)
        seed |= with_geminates(nas)
    seed |= insert_a_between_cons(lower)
    for s in list(seed)[:MAX_ALT]:
        forms |= with_ending(s)
        forms |= with_mid_vowel(s)
        forms |= with_leading_vowel(s)
        forms |= with_trailing_schwa(s)
        forms |= with_retroflex_nasal(s)
        forms |= with_anusvara_nasals(s)
        forms |= with_geminates(s)
        forms |= with_loan_digraphs(s)
        forms |= with_visarga_h(s)
        forms |= apply_confusions(s)
        forms |= insert_a_between_cons(s)
        if len(forms) >= MAX_ALT:
            break
    # Second pass: endings / mid-vowels on newly inserted-a / anusvara forms
    extra: set[str] = set()
    for s in list(forms)[:MAX_ALT]:
        extra |= with_ending(s)
        extra |= with_mid_vowel(s)
        extra |= with_leading_vowel(s)
        extra |= with_trailing_schwa(s)
        extra |= with_retroflex_nasal(s)
        extra |= with_anusvara_nasals(s)
        extra |= with_geminates(s)
        extra |= with_visarga_h(s)
        extra |= insert_a_between_cons(s)
    forms |= extra
    # Cross anusvara × mid-vowel (ziMdabad → ziMdaabaad)
    cross: set[str] = set()
    for s in list(forms):
        if "M" in s or "+" in s:
            cross |= with_double_aa(s)
        if len(cross) + len(forms) >= MAX_ALT * 2:
            break
    forms |= cross
    return forms


def near_exact_suffix(suf: str, full_key: str | None = None, typed_len: int | None = None) -> bool:
    if not suf:
        return False
    if not re.fullmatch(r"(n|m|ng|un|um|h)", suf, flags=re.I):
        return False
    # Short stems: mi+n→min would steal EXACT over phonetic મી/મિ (poshatu≥4 OK).
    if typed_len is not None and typed_len < 4:
        return False
    if typed_len is not None and full_key and len(full_key) > typed_len + len(suf):
        return False
    if full_key and re.fullmatch(r"(n|m)", suf, flags=re.I) and re.search(
        r"(an|en|ian|ing|ers?|ors?|ly)$", full_key, flags=re.I
    ):
        return False
    return True


def is_native_morph_extension(base_native: str, native: str) -> bool:
    if not base_native or not native or native == base_native:
        return False
    return native.startswith(base_native) and len(native) > len(base_native)


LEXICON_STRONG_WEIGHT = 100

# IAST dental↔retroflex place pairs (bare consonant menu).
IAST_PLACE_PAIR = {
    "n": "N",
    "N": "n",
    "t": "T",
    "T": "t",
    "d": "D",
    "D": "d",
    "l": "L",
    "L": "l",
}
IAST_PLACE_GLYPH = {
    "n": "ન",
    "N": "ણ",
    "t": "ત",
    "T": "ટ",
    "d": "દ",
    "D": "ડ",
    "l": "લ",
    "L": "ળ",
}

def is_a_insertion_only(typed: str, key: str) -> bool:
    """Ephemeral schwa inserts only; a→aa lengthening is not weak."""
    if not typed or not key or key == typed or len(key) <= len(typed):
        return False
    i = j = 0
    inserted = 0
    while i < len(typed) and j < len(key):
        if typed[i] == key[j]:
            i += 1
            j += 1
            continue
        if key[j] == "a":
            if j > 0 and key[j - 1] == "a":
                return False
            j += 1
            inserted += 1
            continue
        return False
    if i != len(typed):
        return False
    while j < len(key):
        if key[j] != "a":
            return False
        if j > 0 and key[j - 1] == "a":
            return False
        j += 1
        inserted += 1
    return inserted > 0


def is_digraph_strip_fuzzy(typed: str, hit: str) -> bool:
    if not typed or not hit or len(hit) >= len(typed):
        return False
    pairs = [
        ("chh", "ch"), ("chh", "c"), ("kh", "k"), ("gh", "g"), ("th", "t"), ("dh", "d"),
        ("ph", "p"), ("bh", "b"), ("sh", "s"), ("Sh", "s"), ("Sh", "sh"), ("jh", "j"),
    ]
    t = typed.lower()
    h = hit.lower()
    for long, short in pairs:
        if long not in t:
            continue
        idx = 0
        while idx <= len(t) - len(long):
            at = t.find(long, idx)
            if at < 0:
                break
            if t[:at] + short + t[at + len(long) :] == h:
                return True
            idx = at + 1
    return False


STEM_MATRA_SUFFIXES = [
    ("aa", "ા"),
    ("ii", "ી"),
    ("ee", "ી"),
    ("uu", "ૂ"),
    ("oo", "ૂ"),
    ("ai", "ૈ"),
    ("au", "ૌ"),
    # bare trailing "a" omitted — peels gharma→gharm
    ("i", "િ"),
    ("u", "ુ"),
    ("e", "ે"),
    ("o", "ો"),
]

STEM_POSTFIX_SUFFIXES = [
    ("maanthi", "માંથી"),
    ("maan", "માં"),
    ("maa", "માં"),
    ("man", "માં"),
    ("ma", "માં"),
    ("valun", "વાળું"),
    ("vali", "વાળી"),
    ("vala", "વાળા"),
    ("valo", "વાળો"),
    ("thi", "થી"),
    ("nee", "ની"),
    ("nii", "ની"),
    ("noo", "નું"),
    ("nuu", "નું"),
    ("naa", "ના"),
    ("ni", "ની"),
    ("nu", "નું"),
    ("na", "ના"),
    ("no", "નો"),
    ("ne", "ને"),
]


def _lookup_lexicon_stem(stem: str, lex: dict, weights: dict) -> tuple[str, str, float] | None:
    word = lex.get(stem)
    if word:
        return stem, word, float(weights.get(stem, 100))
    best: tuple[str, str, float] | None = None
    for alt in expand_roman(stem):
        hit = lex.get(alt)
        if not hit:
            continue
        w = float(weights.get(alt, 100))
        if best is None or w > best[2]:
            best = (alt, hit, w)
    return best


def lexicon_stem_matra_hits(typed: str, lex: dict, weights: dict) -> list[tuple[str, str, float]]:
    out: list[tuple[str, str, float]] = []
    lower = typed.lower()
    if len(lower) < 3:
        return out
    for suf, matra in STEM_MATRA_SUFFIXES:
        if len(lower) <= len(suf) + 1 or not lower.endswith(suf):
            continue
        stem = lower[: -len(suf)]
        if len(stem) < 2 or stem[-1] in "aeiou":
            continue
        word = lex.get(stem)
        if not word:
            continue
        w = float(weights.get(stem, 100))
        if matra is None:
            out.append((stem, word, w))
        elif _ends_with_gu_cons(word):
            out.append((stem + suf, word + matra, max(w, 100.0)))
    return out


def lexicon_stem_postfix_hits(typed: str, lex: dict, weights: dict) -> list[tuple[str, str, float]]:
    out: list[tuple[str, str, float]] = []
    lower = typed.lower()
    if len(lower) < 4:
        return out
    for suf, gu_suf in STEM_POSTFIX_SUFFIXES:
        if len(lower) <= len(suf) + 2 or not lower.endswith(suf):
            continue
        stem = lower[: -len(suf)]
        if len(stem) < 2 or stem[-1] in "eiou":
            continue
        if stem.endswith(("aa", "ii", "ee", "uu", "oo", "ai", "au")):
            continue
        hit = _lookup_lexicon_stem(stem, lex, weights)
        if not hit:
            continue
        roman, word, w = hit
        if not _ends_with_gu_cons(word) and not word[-1] in "ાિીુૂેૈોૌં":
            continue
        out.append((roman + suf, word + gu_suf, max(w, 120.0)))
        break
    return out


def lexicon_hit_tier(source: str | None, weight: float, typed: str, hit_roman: str) -> int:
    soft = 0 < weight < LEXICON_STRONG_WEIGHT
    # Bare place-contrast consonant: never EXACT so IAST dental/retroflex twins compete.
    if typed and len(typed) == 1 and typed in IAST_PLACE_PAIR:
        return TIER_DICT
    if source == "strict" and not soft:
        return TIER_EXACT
    if soft:
        return TIER_DICT
    if source == "fuzzy" and typed and hit_roman and is_digraph_strip_fuzzy(typed, hit_roman):
        return TIER_DICT
    # Typed sh… must not promote s… fuzzy to EXACT (shah↛સહ)
    if source == "fuzzy" and typed.startswith("sh") and hit_roman.startswith("s") and not hit_roman.startswith("sh"):
        return TIER_DICT
    if source == "fuzzy" and is_a_insertion_only(typed, hit_roman):
        return TIER_DICT
    # Fuzzy aa-lengthening+inserts (ank→aanak/aanka) must not EXACT-steal.
    if source == "fuzzy" and hit_roman and typed and len(hit_roman) > len(typed) + 1:
        return TIER_DICT
    if source == "stem_matra" or source == "stem_postfix":
        return TIER_EXACT if weight >= LEXICON_STRONG_WEIGHT else TIER_DICT
    if source == "near_exact":
        # Caller skips when typed is already in lexicon; keep EXACT for poshatu→poshatun.
        return TIER_EXACT
    if source in ("fuzzy", "strict"):
        return TIER_EXACT
    return TIER_DICT


ANUSVARA = "\u0A82"
U_MATRA = "\u0AC1"

# Productive conjuncts (Indic IME style); default is inherent schwa.
PRODUCTIVE_CONJUNCTS = {
    ("v", "y"), ("k", "y"), ("g", "y"), ("c", "y"), ("ch", "y"), ("j", "y"),
    ("t", "y"), ("d", "y"), ("n", "y"), ("p", "y"), ("b", "y"), ("m", "y"),
    ("r", "y"), ("l", "y"), ("s", "y"), ("sh", "y"), ("h", "y"), ("T", "y"), ("D", "y"),
    ("p", "r"), ("t", "r"), ("k", "r"), ("g", "r"), ("d", "r"), ("b", "r"), ("s", "r"),
    ("sh", "r"), ("f", "r"), ("ph", "r"),
    ("k", "v"), ("t", "v"), ("d", "v"), ("s", "v"), ("n", "v"), ("dh", "v"),
    ("t", "n"), ("s", "n"), ("s", "t"), ("s", "k"), ("s", "th"), ("t", "th"),
}


def _tokenize_roman(s: str) -> list[str]:
    keys = sorted(list(CONS.keys()) + list(VOW_IND.keys()), key=len, reverse=True)
    i = 0
    toks: list[str] = []
    while i < len(s):
        matched = None
        for t in keys:
            if s.startswith(t, i):
                matched = t
                break
        if matched:
            toks.append(matched)
            i += len(matched)
        else:
            toks.append(s[i])
            i += 1
    return toks


def _is_gu_cons_char(ch: str) -> bool:
    if not ch:
        return False
    o = ord(ch[-1]) if len(ch) > 1 else ord(ch)
    return 0x0A95 <= o <= 0x0AB9 and o not in (0x0AB1, 0x0AB4)


def transliterate(s: str) -> str:
    """Schwa-default phonetic (Apple/Google/MS Indic style) + productive conjuncts."""
    toks = _tokenize_roman(s)
    result = ""
    for i, token in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if token in VOW_IND:
            if result and _is_gu_cons_char(result):
                if token == "a":
                    pass
                else:
                    mat = VOW_MAT.get(token)
                    if mat is not None:
                        result = result[:-1] + result[-1] + mat
                    else:
                        result += VOW_IND[token]
            else:
                result += VOW_IND[token]
        elif token in CONS:
            ch = CONS[token]
            if nxt == "+":
                result += ch + VIRAMA
            elif nxt in CONS and (token, nxt) in PRODUCTIVE_CONJUNCTS:
                result += ch + VIRAMA
            else:
                result += ch
        elif token == "+":
            if result and _is_gu_cons_char(result):
                result += VIRAMA
        elif token in DIGITS:
            result += DIGITS[token]
        else:
            result += token
    return result


def with_visarga_h(s: str) -> set[str]:
    out = {s}
    if not s:
        return out
    for i, ch in enumerate(s):
        if ch not in ("h", "H"):
            continue
        rest = s[i + 1 :]
        if not rest or not re.match(r"^[kKgGcCjJTDdNtnNpPbBmyrRlLvVwsShzfx]", rest):
            continue
        other = "H" if ch == "h" else "h"
        out.add(s[:i] + other + rest)
    return out


def with_nasal_final_u(gu: str) -> str | None:
    if not gu or gu.endswith(U_MATRA + ANUSVARA):
        return None
    if gu.endswith(U_MATRA):
        return gu + ANUSVARA
    return None


def _ends_with_gu_cons(s: str) -> bool:
    if not s:
        return False
    return _is_gu_cons_char(s[-1])


def diphthong_alternate_forms(roman: str) -> list[str]:
    """Mirror JS: ai/ay/oi/ui/ei → independent ઈ/ઇ splits."""
    out: list[str] = []
    if not roman:
        return out
    s = roman.lower()
    for digraph in ("ai", "ay", "oi", "ui", "ei"):
        idx = 0
        added = 0
        while idx <= len(s) - len(digraph) and added < 3:
            at = s.find(digraph, idx)
            if at < 0:
                break
            if at > 0 and s[at - 1] == "a" and digraph == "ai":
                idx = at + 1
                continue
            prefix, suffix = s[:at], s[at + len(digraph) :]
            prefix_gu = transliterate(prefix) if prefix else ""
            suffix_gu = transliterate(suffix) if suffix else ""
            nuclei: list[str] = []
            if digraph == "ai":
                if not prefix_gu:
                    nuclei.extend(["ઐ", "અઈ", "અઇ", "આઈ", "આઇ"])
                elif _ends_with_gu_cons(prefix_gu):
                    nuclei.extend([prefix_gu + "ઈ", prefix_gu + "ઇ"])
                    with_aa = prefix_gu[:-1] + prefix_gu[-1] + VOW_MAT["aa"]
                    nuclei.extend([with_aa + "ઈ", with_aa + "ઇ"])
            elif digraph == "ay":
                if not prefix_gu:
                    nuclei.extend(["અય", "આય"])
                elif _ends_with_gu_cons(prefix_gu):
                    nuclei.append(prefix_gu + "ય")
                    with_aa = prefix_gu[:-1] + prefix_gu[-1] + VOW_MAT["aa"]
                    nuclei.append(with_aa + "ય")
            elif digraph in ("oi", "ui", "ei"):
                if _ends_with_gu_cons(prefix_gu):
                    mat = {"oi": "o", "ui": "u", "ei": "e"}[digraph]
                    with_matra = prefix_gu[:-1] + prefix_gu[-1] + VOW_MAT[mat]
                    nuclei.extend([with_matra + "ઈ", with_matra + "ઇ"])
                    if digraph == "ui":
                        with_uu = prefix_gu[:-1] + prefix_gu[-1] + VOW_MAT["uu"]
                        nuclei.extend([with_uu + "ઈ", with_uu + "ઇ"])
            for n in nuclei:
                out.append(n + suffix_gu)
            if nuclei:
                added += 1
            idx = at + 1
    return out


def phonetic_forms(roman: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(g: str | None) -> None:
        if not g or g == roman or g in seen:
            return
        seen.add(g)
        out.append(g)

    base = transliterate(roman)
    add(base)
    add(with_nasal_final_u(base) if base else None)
    for g in diphthong_alternate_forms(roman):
        add(g)
        add(with_nasal_final_u(g))
    return out


def gu_orthography_penalty(text: str) -> float:
    if not text:
        return 0.0
    pen = 0.0
    matra = re.compile(r"[\u0ABE-\u0ACC\u0AE2\u0AE3]")
    if matra.match(text[0]):
        pen += 3.0
    for i in range(len(text) - 1):
        a, b = text[i], text[i + 1]
        if a == VIRAMA and b == VIRAMA:
            pen += 2.5
        if matra.match(a) and matra.match(b):
            pen += 2.0
    return pen


def dictionary_validity(text: str, uni: dict[str, int], stems: dict[str, int], attested: set[str], floor: int) -> dict:
    if not text:
        return {"score": 0.0, "attested": False, "spell_ok": False, "evidence": 0, "uni_strong": False}
    text = text.encode("utf-8").decode("utf-8")
    try:
        text = unicodedata.normalize("NFC", text)
    except Exception:
        pass
    uni_c = uni.get(text, 0)
    spell_ok = text in attested
    spell_hit = floor if spell_ok else 0
    stem_hit = stems.get(text, 0)
    stem_real = stems.get(text, 0)
    if spell_ok:
        stem_hit = max(stem_hit, floor)
    for suf in GU_SUFFIXES:
        if len(text) <= len(suf) + 1 or not text.endswith(suf):
            continue
        stem = text[: -len(suf)]
        if not stem:
            continue
        sf = stems.get(stem, 0)
        stem_real = max(stem_real, sf)
        stem_hit = max(stem_hit, sf)
        if stem in attested:
            stem_hit = max(stem_hit, floor)
        for ext in ["ે", "ો", "ા", "ી", "ું", "વું", "તું", "વા", "શે", "શો"]:
            form = stem + ext
            fu = uni.get(form, 0)
            fs = stems.get(form, 0)
            stem_hit = max(stem_hit, fu, fs)
            if fu > floor:
                stem_real = max(stem_real, fu)
            stem_real = max(stem_real, fs)
            if form in attested:
                stem_hit = max(stem_hit, floor)
    evidence = max(uni_c, stem_hit, spell_hit)
    uni_strong = uni_c > floor
    # Direct unigram (incl. soft floor) still attests; sole attested.json pad without uni/stem does not.
    attested_flag = uni_c > 0 or stem_real > 0 or (spell_ok and uni_strong)
    virama = text.count(VIRAMA)
    # Prefer full-word unigram over stem-only (વિકસ stem must not beat વિકાસ uni).
    score = (
        math.log1p(uni_c)
        + math.log1p(spell_hit) * 0.35
        + math.log1p(stem_hit) * (0.35 if uni_c > 0 else 0.7)
        - virama * 0.25
        - gu_orthography_penalty(text)
    )
    return {
        "score": max(0.0, score),
        "attested": attested_flag,
        "spell_ok": spell_ok,
        "evidence": evidence,
        "uni_strong": uni_strong,
    }


def rank(input_s: str, blob: dict, uni: dict, stems: dict, attested: set[str], floor: int,
         prefix_index: dict[str, list[tuple[str, str]]] | None = None) -> list[tuple[str, int, float]]:
    lex = blob.get("lexicon") or {}
    weights = blob.get("weights") or {}
    exceptions = blob.get("exceptions") or {}
    lower = input_s.lower()
    queries = expand_roman(input_s)

    cands: list[dict] = []
    seen: set[str] = set()

    def push(text: str, tier: int, weight: float, source: str | None, roman_key: str):
        if not text or text in seen:
            return
        seen.add(text)
        cands.append({"text": text, "tier": tier, "weight": weight, "source": source, "roman": roman_key})

    if lower in exceptions:
        push(exceptions[lower], TIER_EXACT, 1000, "strict", lower)

    exact_hits = []
    for q in queries:
        if q in lex:
            src = "strict" if q == lower else "fuzzy"
            exact_hits.append((q, lex[q], float(weights.get(q, 100)), src))
    # near-exact: typed + weak suffix only (poshatu→poshatun). Skip when typed is
    # already in the lexicon (ghar+m/gnan+m must not steal EXACT). Do not apply on
    # vowel-length expansions (ank↛aankh).
    typed_in_lex = lower in lex or input_s in lex
    if not typed_in_lex:
        for q in (lower, input_s):
            if len(q) < 2:
                continue
            bucket = (
                prefix_index.get(q[:2], [])
                if prefix_index is not None
                else [(k, lex[k]) for k in lex if k.startswith(q[:2])]
            )
            for key, word in bucket:
                if not key.startswith(q):
                    continue
                suf = key[len(q) :]
                if near_exact_suffix(suf, key, len(q)):
                    exact_hits.append((key, word, float(weights.get(key, 100)), "near_exact"))

    exact_hits.sort(key=lambda x: (0 if x[3] == "strict" else 1, -x[2], len(x[0])))
    for roman, word, w, src in exact_hits:
        tier = lexicon_hit_tier(src, w, lower if len(input_s) != 1 else input_s, roman)
        # Upgrade if same native already pushed at a weaker tier
        existing = next((c for c in cands if c["text"] == word), None)
        if existing:
            if tier < existing["tier"]:
                existing["tier"] = tier
                existing["source"] = src
                existing["weight"] = max(existing["weight"], w)
                existing["roman"] = roman
            continue
        push(word, tier, w, src, roman)

    for stem_roman, word, w in lexicon_stem_matra_hits(lower, lex, weights):
        tier = lexicon_hit_tier("stem_matra", w, lower if len(input_s) != 1 else input_s, stem_roman)
        existing = next((c for c in cands if c["text"] == word), None)
        if existing:
            if tier < existing["tier"]:
                existing["tier"] = tier
                existing["source"] = "stem_matra"
                existing["weight"] = max(existing["weight"], w)
                existing["roman"] = stem_roman
            continue
        push(word, tier, w, "stem_matra", stem_roman)

    for stem_roman, word, w in lexicon_stem_postfix_hits(lower, lex, weights):
        tier = lexicon_hit_tier("stem_postfix", w, lower if len(input_s) != 1 else input_s, stem_roman)
        existing = next((c for c in cands if c["text"] == word), None)
        if existing:
            if tier < existing["tier"]:
                existing["tier"] = tier
                existing["source"] = "stem_postfix"
                existing["weight"] = max(existing["weight"], w)
                existing["roman"] = stem_roman
            continue
        push(word, tier, w, "stem_postfix", stem_roman)

    has_strict = any(c["source"] == "strict" for c in cands if c["tier"] == TIER_EXACT)
    exact_count = sum(1 for c in cands if c["tier"] == TIER_EXACT)

    phon_forms = []
    # Prefer anusvara/geminate rewrites + near-length fuzzy queries
    ordered_q = sorted(
        queries,
        key=lambda q: (
            0 if ("M" in q or "+" in q) else 1,
            abs(len(q) - len(lower)),
            q != lower,
            q,
        ),
    )
    twin_q = []
    if len(input_s) == 1 and input_s in IAST_PLACE_PAIR:
        twin_q.append(IAST_PLACE_PAIR[input_s])
    elif len(lower) == 1 and lower in IAST_PLACE_PAIR:
        twin_q.append(IAST_PLACE_PAIR[lower])
    for form in [input_s, *twin_q, *[q for q in ordered_q if q != input_s][:80]]:
        for g in phonetic_forms(form):
            if g not in phon_forms:
                phon_forms.append(g)

    phon_scored = []
    for text in phon_forms:
        if text in seen:
            continue
        v = dictionary_validity(text, uni, stems, attested, floor)
        # Keep attested/spell even when lexicon EXACT exists (n→ણ must not hide ન).
        if exact_count > 0 and has_strict and not v["attested"] and not v["spell_ok"]:
            continue
        phon_scored.append((text, v))
    phon_scored.sort(
        key=lambda x: (
            -int((uni.get(x[0], 0) or 0) > floor),
            -int(x[1]["spell_ok"]),
            -int(x[1]["attested"]),
            -uni.get(x[0], 0),
            -x[1]["score"],
            -x[0].count("ા"),
            -x[0].count("ં"),
        )
    )
    # Strong strict EXACT → keep only best uni-backed phonetics (menu budget).
    has_strong_exact = any(
        c["source"] == "strict" and c["weight"] >= LEXICON_STRONG_WEIGHT and c["tier"] == TIER_EXACT
        for c in cands
    )
    phon_limit = 2 if has_strong_exact else 12
    uni_backed = 0
    added_phon = 0
    for text, v in phon_scored:
        if added_phon >= phon_limit:
            break
        uc = uni.get(text, 0)
        if uni_backed >= 2 and uc <= floor and not v.get("uni_strong"):
            continue
        tier = TIER_DICT if v["attested"] else TIER_PHONETIC
        push(text, tier, v["evidence"], None, lower)
        added_phon += 1
        if v.get("uni_strong") or uc > floor:
            uni_backed += 1

    scored = []
    for i, c in enumerate(cands):
        v = dictionary_validity(c["text"], uni, stems, attested, floor)
        dict_boost = v["score"] * 1.4 if v["attested"] else 0.0
        # Prefer full-word unigram magnitude in ranking (wikas: વિકાસ@400 > વિકાશ@50)
        uni_c = uni.get(c["text"], 0)
        uni_boost = math.log1p(uni_c) * 0.55
        spell_boost = 0.35 if v["spell_ok"] else 0.0
        freq = math.log1p(c["weight"]) * 0.35
        score = freq + dict_boost + uni_boost + spell_boost
        # Soft-fill lexicon only (not phonetics — phon weight is uni evidence)
        is_lex = c.get("source") in ("strict", "fuzzy", "near_exact", "stem_matra", "stem_postfix")
        if is_lex and 0 < c["weight"] < LEXICON_STRONG_WEIGHT and uni_c < 150:
            score -= freq * 0.85 + 2.8
        if is_lex and 0 < c["weight"] < LEXICON_STRONG_WEIGHT and "ય" in c["text"] and "y" not in lower:
            score -= 4.0
        # Soft typed lexicon only when competing with digraph-strip fuzzy (vinash vs vinas),
        # not for mid-vowel soft keys (swagat vs swaagat / gharma vs gharmaan).
        typed_w = float(weights.get(lower, 0) or 0)
        typed_lex = lex.get(lower) or exceptions.get(lower)
        if (
            0 < typed_w < LEXICON_STRONG_WEIGHT
            and typed_lex == c["text"]
            and any(
                o.get("roman") and is_digraph_strip_fuzzy(lower, o["roman"])
                for o in cands
            )
        ):
            score += 3.2
        # Prefer Apple bare stems over morph extensions; skip soft / bare IAST.
        scored_tier = c["tier"]
        bare_iast = len(input_s) == 1 and input_s in IAST_PLACE_PAIR
        if typed_lex and typed_w >= LEXICON_STRONG_WEIGHT and not bare_iast:
            competing_morph = any(
                is_native_morph_extension(typed_lex, o["text"]) for o in cands
            )
            if c["text"] == typed_lex and competing_morph:
                score += 6.5
            elif is_native_morph_extension(typed_lex, c["text"]):
                score -= 8.5
                if scored_tier == TIER_EXACT:
                    scored_tier = TIER_DICT
        if (
            c.get("source") == "near_exact"
            and typed_lex
            and typed_w >= LEXICON_STRONG_WEIGHT
            and c["text"] != typed_lex
            and c.get("roman")
            and len(c["roman"]) > len(lower)
        ):
            score -= 7.0
            if scored_tier == TIER_EXACT:
                scored_tier = TIER_DICT
        if is_lex and c.get("roman") == lower and typed_w >= LEXICON_STRONG_WEIGHT:
            score += 2.0
        elif is_lex and c.get("roman") and len(c["roman"]) > len(lower) + 1:
            score -= 1.5
        # Inserted ya-phala not typed — any source
        if "ય" in c["text"] and "y" not in lower:
            score -= 4.0
        # IAST case for bare place-contrast letters (n→ન over ણ, N→ણ over ન).
        if len(input_s) == 1 and input_s in IAST_PLACE_GLYPH:
            prefer = IAST_PLACE_GLYPH[input_s]
            twin = IAST_PLACE_GLYPH.get(IAST_PLACE_PAIR[input_s])
            if c["text"] == prefer:
                score += 2.5
            elif twin and c["text"] == twin:
                score -= 0.35
        # Typed dental d → prefer દ over ડ
        if "d" in lower and not re.search(r"(^|[^a-z])D", lower):
            if "ડ" in c["text"] and "દ" not in c["text"]:
                score -= 1.2
            if "દ" in c["text"]:
                score += 0.5
        # Typed sh → prefer શ over સ (claw back high-uni સહ)
        if lower.startswith("sh"):
            if c["text"].startswith("શ"):
                score += 3.0
            elif c["text"].startswith("સ"):
                score -= 3.0 + uni_boost * 0.5
        # Typed plain s (not sh) → prefer સ over શ
        elif "sh" not in lower and "s" in lower:
            if "શ" in c["text"] and "ષ" not in c["text"]:
                score -= 0.55
            if c["text"].count("સ") and "શ" not in c["text"]:
                score += 0.2
        # Typed z → prefer ઝ over જ
        if "z" in lower and "j" not in lower:
            if c["text"].startswith("ઝ"):
                score += 0.5
            elif c["text"].startswith("જ"):
                score -= 0.35
        # Geminate roman → prefer virama geminate; demote anusvara lexicon hits hard
        # (himmat: હિમ્મત over high-uni હિંમત).
        if re.search(r"(mm|nn|tt|kk|ll)", lower):
            if VIRAMA in c["text"]:
                score += 5.5
            if "ં" in c["text"] and VIRAMA not in c["text"]:
                score -= 6.5 + uni_boost * 1.15
                if scored_tier == TIER_EXACT:
                    scored_tier = TIER_DICT
        elif "ં" in c["text"] and re.search(r"n[kgcjtdTDpb]", lower):
            score += 0.35
        # Typed aa… → prefer આ over અ (aadas→આડસ); short-a cannot stay EXACT
        if lower.startswith("aa"):
            if c["text"].startswith("આ"):
                score += 3.5
            elif c["text"].startswith("અ"):
                score -= 4.0
                if scored_tier == TIER_EXACT:
                    scored_tier = TIER_DICT
        elif re.match(
            r"^(?:[kgcjtdTDpbnmylrsvwxyz]|ch|kh|gh|jh|th|dh|ph|bh|sh|Sh|tr|dr)a(?!a)",
            lower,
            re.I,
        ):
            # Short-a onset + later a: demote onset-only long-a (પારખવ્યું not બાંદા).
            t = c["text"]
            lead_long = t.startswith("આ") or (
                len(t) >= 2 and "\u0A95" <= t[0] <= "\u0AB9" and t[1] == "ા"
            )
            if lead_long:
                rest = t[1:] if t.startswith("આ") else t[2:]
                if "ા" not in rest and re.search(r"a(?!a)", lower[2:]):
                    score -= 3.8
        # Prefer long-a; ignore spurious trailing આ when roman doesn't end in a
        a_vowels = len(re.findall(r"a+", lower))
        aa_count = c["text"].count("ા")
        effective_aa = aa_count
        if c["text"].endswith("ા") and not lower.endswith(("a", "aa")):
            effective_aa = max(0, effective_aa - 1)
            score -= 1.6
        if a_vowels >= 1 and "a" in lower[1:]:
            score += 0.2 * effective_aa
            if a_vowels >= 2 and effective_aa >= 2:
                score += 2.5
            elif a_vowels >= 2 and effective_aa < 2:
                score -= 1.2
        # Length: avoid dropping vowels to short anusvara junk (banda↛બંડ)
        if len(c["text"]) < len(lower) * 0.7:
            score -= 2.0
        scored.append((c["text"], scored_tier, score, c["weight"], i))

    scored.sort(key=lambda x: (x[1], -x[2], -x[3], x[4]))
    return [(t, tier, sc) for t, tier, sc, _w, _i in scored]


def build_prefix_index(lex: dict) -> dict[str, list[tuple[str, str]]]:
    idx: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for k, v in lex.items():
        if len(k) >= 2:
            idx[k[:2]].append((k, v))
    return idx


def main() -> int:
    for p in (BLOB, UNI, STEMS, ATTESTED):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 2

    blob = load_blob()
    uni = load_unigram()
    stems = load_stems()
    attested, floor = load_attested()
    prefix_index = build_prefix_index(blob.get("lexicon") or {})
    print(f"lex={len(blob.get('lexicon') or {})} uni={len(uni)} stems={len(stems)} attested={len(attested)}")

    smoke_results = []
    smoke_ok = 0
    for roman, expect in SMOKE:
        ranked = rank(roman, blob, uni, stems, attested, floor, prefix_index)
        top = ranked[0][0] if ranked else None
        ok = top == expect
        smoke_ok += int(ok)
        smoke_results.append({"input": roman, "expected": expect, "top1": top, "ok": ok, "top5": [r[0] for r in ranked[:5]]})
        print(f"  smoke {roman}: top1={top} expected={expect} {'OK' if ok else 'FAIL'}")

    # Held-out: fuzzy transform of known lexicon keys (drop exact key, expect same word via fuzzy)
    oov_ok = oov_n = 0
    lex = blob.get("lexicon") or {}
    samples = []
    for roman, word in list(lex.items())[:5000]:
        if len(roman) < 4 or len(roman) > 10:
            continue
        # apply one confusion if possible
        alts = apply_confusions(roman) - {roman}
        if not alts:
            continue
        alt = sorted(alts, key=len)[0]
        if alt in lex:
            continue
        samples.append((alt, word))
        if len(samples) >= 40:
            break
    for alt, word in samples:
        ranked = rank(alt, blob, uni, stems, attested, floor, prefix_index)
        top = ranked[0][0] if ranked else None
        oov_n += 1
        oov_ok += int(top == word)

    oov_rate = (oov_ok / oov_n) if oov_n else 0.0
    print(f"fuzzy-oov top1={oov_ok}/{oov_n} ({oov_rate:.1%})")

    payload = {
        "smoke_ok": smoke_ok,
        "smoke_total": len(SMOKE),
        "smoke": smoke_results,
        "fuzzy_oov_ok": oov_ok,
        "fuzzy_oov_total": oov_n,
        "fuzzy_oov_rate": oov_rate,
        "attested_size": len(attested),
        "unigram_size": len(uni),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT}")

    if smoke_ok < len(SMOKE):
        print("SMOKE FAILED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
