#!/usr/bin/env python3
"""Offline ranking eval mirroring gujarati_translator.js policy (v2.7).

Loads lexicon blob + unigram + stems + attested. Checks smoke top-1 and a
small OOV/fuzzy sample. Does not require Rime/Squirrel.
"""
from __future__ import annotations

import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOB = ROOT / "rime" / "gu_lexicon_blob.json"
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
    "ksh": "ક્ષ", "x": "ક્ષ", "gy": "જ્ઞ", "chh": "છ", "ch": "ચ", "c": "ચ",
    "kh": "ખ", "k": "ક", "gh": "ઘ", "g": "ગ", "ng": "ઙ",
    "jh": "ઝ", "j": "જ", "ny": "ઞ", "Th": "ઠ", "T": "ટ", "Dh": "ઢ", "D": "ડ", "N": "ણ",
    "th": "થ", "t": "ત", "dh": "ધ", "d": "દ", "n": "ન",
    "ph": "ફ", "f": "ફ", "p": "પ", "bh": "ભ", "b": "બ", "m": "મ",
    "y": "ય", "r": "ર", "L": "ળ", "l": "લ", "v": "વ", "w": "વ",
    "sh": "શ", "Sh": "ષ", "s": "સ", "h": "હ", "z": "ઝ",
}
VOW_IND = {
    "aa": "આ", "ii": "ઈ", "ee": "ઈ", "uu": "ઊ", "oo": "ઊ", "ai": "ઐ", "au": "ઔ",
    "a": "અ", "i": "ઇ", "u": "ઉ", "e": "એ", "o": "ઓ",
}
VOW_MAT = {
    "aa": "ા", "ii": "ી", "ee": "ી", "uu": "ૂ", "oo": "ૂ", "ai": "ૈ", "au": "ૌ",
    "i": "િ", "u": "ુ", "e": "ે", "o": "ો",
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
]


def load_blob() -> dict:
    return json.loads(BLOB.read_text(encoding="utf-8"))


def load_unigram() -> dict[str, int]:
    m: dict[str, int] = {}
    for line in UNI.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        m[parts[0]] = int(parts[1])
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
    for frm, to in [("i", "ii"), ("ii", "i"), ("a", "aa"), ("aa", "a")]:
        idx, added = 0, 0
        while idx <= len(s) - len(frm) and added < 4:
            at = s.find(frm, idx)
            if at < 0:
                break
            if at > 0:
                if frm in ("i", "ii") and is_diphthong_i(s, at):
                    idx = at + 1
                    continue
                out.add(s[:at] + to + s[at + len(frm) :])
                added += 1
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


def expand_roman(input_s: str) -> set[str]:
    lower = input_s.lower()
    forms = {lower, input_s}
    seed = set(with_ending(lower)) | set(with_mid_vowel(lower)) | apply_confusions(lower)
    seed |= insert_a_between_cons(lower)
    for s in list(seed)[:MAX_ALT]:
        forms |= with_ending(s)
        forms |= with_mid_vowel(s)
        forms |= apply_confusions(s)
        forms |= insert_a_between_cons(s)
        if len(forms) >= MAX_ALT:
            break
    # Second pass: endings / mid-vowels on newly inserted-a forms (ketli→keTali→keTalii)
    extra: set[str] = set()
    for s in list(forms)[:MAX_ALT]:
        extra |= with_ending(s)
        extra |= with_mid_vowel(s)
        extra |= insert_a_between_cons(s)
    forms |= extra
    return forms


def near_exact_suffix(suf: str) -> bool:
    if not suf:
        return False
    return bool(re.fullmatch(r"(n|m|ng|un|um|h)", suf, flags=re.I))


LEXICON_STRONG_WEIGHT = 100


def is_a_insertion_only(typed: str, key: str) -> bool:
    if not typed or not key or key == typed or len(key) <= len(typed):
        return False
    i = j = 0
    while i < len(typed) and j < len(key):
        if typed[i] == key[j]:
            i += 1
            j += 1
            continue
        if key[j] == "a":
            j += 1
            continue
        return False
    if i != len(typed):
        return False
    return all(c == "a" for c in key[j:])


def lexicon_hit_tier(source: str | None, weight: float, typed: str, hit_roman: str) -> int:
    soft = 0 < weight < LEXICON_STRONG_WEIGHT
    if source == "strict" and not soft:
        return TIER_EXACT
    if soft:
        return TIER_DICT
    if source == "fuzzy" and is_a_insertion_only(typed, hit_roman):
        return TIER_DICT
    if source in ("near_exact", "fuzzy", "strict"):
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
    ("t", "n"), ("s", "n"), ("s", "t"), ("s", "k"),
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
        else:
            result += token
    return result


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
    """Mirror JS: ai/ay → અઈ/ાઈ/ાય splits the matra transliterator cannot emit."""
    out: list[str] = []
    if not roman:
        return out
    s = roman.lower()
    for digraph in ("ai", "ay"):
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


def dictionary_validity(text: str, uni: dict[str, int], stems: dict[str, int], attested: set[str], floor: int) -> dict:
    if not text:
        return {"score": 0.0, "attested": False, "spell_ok": False, "evidence": 0}
    uni_c = uni.get(text, 0)
    spell_ok = text in attested
    spell_hit = floor if spell_ok else 0
    stem_hit = stems.get(text, 0)
    if spell_ok:
        stem_hit = max(stem_hit, floor)
    for suf in GU_SUFFIXES:
        if len(text) <= len(suf) + 1 or not text.endswith(suf):
            continue
        stem = text[: -len(suf)]
        if not stem:
            continue
        stem_hit = max(stem_hit, stems.get(stem, 0))
        if stem in attested:
            stem_hit = max(stem_hit, floor)
        for ext in ["ે", "ો", "ા", "ી", "ું", "વું", "તું", "વા", "શે", "શો"]:
            form = stem + ext
            stem_hit = max(stem_hit, uni.get(form, 0), stems.get(form, 0))
            if form in attested:
                stem_hit = max(stem_hit, floor)
    evidence = max(uni_c, stem_hit, spell_hit)
    virama = text.count(VIRAMA)
    score = max(0.0, math.log1p(evidence) - virama * 0.25)
    return {"score": score, "attested": evidence > 0 or spell_ok, "spell_ok": spell_ok, "evidence": evidence}


def rank(input_s: str, blob: dict, uni: dict, stems: dict, attested: set[str], floor: int) -> list[tuple[str, int, float]]:
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
    # near-exact: lexicon keys that start with query + weak suffix
    for q in queries:
        if len(q) < 2:
            continue
        for key, word in lex.items():
            if not key.startswith(q):
                continue
            suf = key[len(q) :]
            if near_exact_suffix(suf):
                exact_hits.append((key, word, float(weights.get(key, 100)), "near_exact"))

    exact_hits.sort(key=lambda x: (-x[2], len(x[0])))
    for roman, word, w, src in exact_hits:
        tier = lexicon_hit_tier(src, w, lower, roman)
        push(word, tier, w, src, roman)

    has_strict = any(c["source"] == "strict" for c in cands if c["tier"] == TIER_EXACT)
    exact_count = sum(1 for c in cands if c["tier"] == TIER_EXACT)

    phon_forms = []
    # Prefer near-length fuzzy queries (parkhaavyu before paaaarkhavyu); mirrors JS
    # iterating altForms while avoiding hash-order flakes in Python sets.
    ordered_q = sorted(queries, key=lambda q: (abs(len(q) - len(lower)), q != lower, q))
    for form in [input_s, *[q for q in ordered_q if q != input_s][:60]]:
        for g in phonetic_forms(form):
            if g not in phon_forms:
                phon_forms.append(g)

    phon_scored = []
    for text in phon_forms:
        if text in seen:
            continue
        v = dictionary_validity(text, uni, stems, attested, floor)
        if exact_count > 0 and has_strict and not v["attested"] and not v["spell_ok"]:
            continue
        phon_scored.append((text, v))
    phon_scored.sort(key=lambda x: (-int(x[1]["spell_ok"]), -int(x[1]["attested"]), -x[1]["score"]))
    for text, v in phon_scored[:5]:
        tier = TIER_DICT if v["attested"] else TIER_PHONETIC
        push(text, tier, v["evidence"], None, lower)

    scored = []
    for i, c in enumerate(cands):
        v = dictionary_validity(c["text"], uni, stems, attested, floor)
        dict_boost = v["score"] * 1.4 if v["attested"] else 0.0
        spell_boost = 0.35 if v["spell_ok"] else 0.0
        freq = math.log1p(c["weight"]) * 0.35
        score = freq + dict_boost + spell_boost
        scored.append((c["text"], c["tier"], score, c["weight"], i))

    scored.sort(key=lambda x: (x[1], -x[2], -x[3], x[4]))
    return [(t, tier, sc) for t, tier, sc, _w, _i in scored]


def main() -> int:
    for p in (BLOB, UNI, STEMS, ATTESTED):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 2

    blob = load_blob()
    uni = load_unigram()
    stems = load_stems()
    attested, floor = load_attested()
    print(f"lex={len(blob.get('lexicon') or {})} uni={len(uni)} stems={len(stems)} attested={len(attested)}")

    smoke_results = []
    smoke_ok = 0
    for roman, expect in SMOKE:
        ranked = rank(roman, blob, uni, stems, attested, floor)
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
        ranked = rank(alt, blob, uni, stems, attested, floor)
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
