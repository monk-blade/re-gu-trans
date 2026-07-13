#!/usr/bin/env python3
"""Distill Apple Gujarati transliteration data into Rime-ready lexicons."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RIME_OUT = ROOT / "rime"
HOME_RIME = Path.home() / "Library" / "Rime"

GU_RE = re.compile(r"[\u0A80-\u0AFF]+")


def load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def parse_rime_dict(path: Path) -> list[tuple[str, str, int]]:
    """Parse gujarati\\troman\\tweight lines from a Rime dict yaml."""
    rows: list[tuple[str, str, int]] = []
    if not path.exists():
        return rows
    in_body = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip() == "...":
            in_body = True
            continue
        if not in_body:
            # also accept body without ...
            if "\t" in line and not line.startswith("#") and not line.startswith("---"):
                parts = line.split("\t")
                if len(parts) >= 2 and GU_RE.search(parts[0]):
                    in_body = True
                else:
                    continue
            else:
                continue
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        gu, roman = parts[0].strip(), parts[1].strip().lower()
        if not gu or not roman or not GU_RE.search(gu):
            continue
        weight = 100
        if len(parts) >= 3:
            try:
                weight = int(float(parts[2]))
            except ValueError:
                weight = 100
        rows.append((gu, roman, weight))
    return rows


def parse_required_exceptions_tokens(path: Path) -> dict[str, str]:
    """Best-effort: pair latin suffixes with following Gujarati from token dump."""
    # Format from earlier extract: L\\tfrag / G\\tword interleaved poorly.
    # Prefer Apple probe results; this is only a weak fallback.
    return {}


def build_probe_wordlist() -> Path:
    words: set[str] = set()
    # Seed from existing WORD_DICT
    seed = DATA / "seed_word_dict.tsv"
    if seed.exists():
        for line in load_lines(seed):
            parts = line.split("\t")
            if len(parts) >= 2:
                words.add(parts[1].lower())
            elif len(parts) == 1:
                words.add(parts[0].lower())

    # From Rime extra dict codes
    for name in (
        "gujarati_extra.dict.yaml",
        "gujarati.dict.yaml",
        "gujarati_emoji.dict.yaml",
        "gujarati_learned.dict.yaml",
        "gujarati_auto.dict.yaml",
    ):
        for _gu, roman, _w in parse_rime_dict(HOME_RIME / name):
            if 1 <= len(roman) <= 40 and roman.isascii():
                words.add(roman)

    # Common Gujarati romanizations / Apple-style spellings
    extras = """
    kem kemcho namaste gujarat aavjo madad bhai ben prem pyar
    tame hu chu chhe shu kyare dhanyavad mumbai ahmedabad saru majha
    school computer india hello thanks please pan ane athva
    aaj kale ghar kaam paani rotli cha majja saru chhe
    gujarati bharat hindustan surat vadodara rajkot
    maa bapu dikro dikri beno bhaio mitra
    aavu jau karu thai thai gayu aavyo aavi
    shubh prabhat shubh ratri kem chho majama
    laptop mobile phone email internet
    doctor hospital medicine university college
    """.split()
    words.update(w.lower() for w in extras if w.isalpha())

    # Cap for Apple probe latency; prefer shorter / seed words first
    sorted_words = sorted(words, key=lambda w: (len(w), w))
    if len(sorted_words) > 12000:
        sorted_words = sorted_words[:12000]
    out = DATA / "probe_wordlist.txt"
    out.write_text("\n".join(sorted_words) + "\n", encoding="utf-8")
    print(f"probe wordlist: {len(sorted_words)} -> {out}")
    return out


def compile_and_run_probe(wordlist: Path) -> Path:
    src = ROOT / "scripts" / "probe_tl.m"
    bin_path = ROOT / "tools" / "probe_tl"
    bin_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        [
            "clang",
            "-fobjc-arc",
            "-framework",
            "Foundation",
            "-O2",
            "-o",
            str(bin_path),
            str(src),
        ]
    )
    out = DATA / "apple_probe.tsv"
    with out.open("w", encoding="utf-8") as fh:
        subprocess.check_call([str(bin_path), str(wordlist)], stdout=fh)
    print(f"apple probe: {out} ({sum(1 for _ in out.open())} lines)")
    return out


def distill_phonetic_rules() -> Path:
    mappings = json.loads((ROOT / "gu-Mappings.json").read_text(encoding="utf-8"))
    # Prefer first non-empty Gujarati mapping per key; keep all variants
    rules: dict[str, list[str]] = {}
    for key, vals in mappings.items():
        if not key.isalpha() and key not in {"aa", "ai", "au", "ee", "oo"}:
            # keep letter digraphs only for phonetic engine
            if not all(c.isalpha() for c in key):
                continue
        cleaned = []
        for v in vals:
            if not v:
                continue
            if GU_RE.search(v) or v in ("ં", "ઃ", "્"):
                if v not in cleaned:
                    cleaned.append(v)
        if cleaned:
            rules[key] = cleaned
    out = DATA / "gu_phonetic_rules.json"
    out.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"phonetic rules: {len(rules)} keys -> {out}")
    return out


def distill_all() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    RIME_OUT.mkdir(parents=True, exist_ok=True)

    distill_phonetic_rules()
    wordlist = build_probe_wordlist()
    probe_tsv = compile_and_run_probe(wordlist)

    # exceptions: type==1 from Apple probe (Exception)
    exceptions: dict[str, str] = {}
    lexicon: dict[str, tuple[str, int]] = {}  # roman -> (gu, weight)
    train_rows: list[dict] = []

    by_input: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for line in load_lines(probe_tsv):
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        inp, gu, typ_s = parts[0].lower(), parts[1], parts[2]
        lm = parts[3] if len(parts) > 3 else "0"
        try:
            typ = int(typ_s)
        except ValueError:
            continue
        if not GU_RE.search(gu):
            continue
        by_input[inp].append((gu, typ, lm))
        if typ == 1:
            exceptions[inp] = gu
            lexicon[inp] = (gu, 1000)
        elif typ == 0:
            # lexicon-quality from Apple
            if inp not in lexicon:
                lexicon[inp] = (gu, 800)

    # Seed WORD_DICT
    for line in load_lines(DATA / "seed_word_dict.tsv"):
        parts = line.split("\t")
        if len(parts) >= 2:
            gu, roman = parts[0], parts[1].lower()
            if roman not in lexicon:
                lexicon[roman] = (gu, 900)

    # sp.dat surface forms — no roman; skip pairing (used as gu-only boost list)
    sp_words = load_lines(ROOT / "gu_sp_lexicon.txt")

    # Rime extra dict
    for name in ("gujarati_extra.dict.yaml", "gujarati.dict.yaml", "gujarati_learned.dict.yaml"):
        for gu, roman, weight in parse_rime_dict(HOME_RIME / name):
            if roman not in lexicon or weight > lexicon[roman][1]:
                # don't override Apple exceptions
                if roman in exceptions:
                    continue
                lexicon[roman] = (gu, min(weight, 700))

    # Write exceptions.tsv
    exc_path = DATA / "gu_exceptions.tsv"
    exc_path.write_text(
        "\n".join(f"{gu}\t{roman}\t1000" for roman, gu in sorted(exceptions.items(), key=lambda x: x[0]))
        + "\n",
        encoding="utf-8",
    )
    print(f"exceptions: {len(exceptions)} -> {exc_path}")

    # Write lexicon.tsv  gujarati\\troman\\tweight
    lex_path = DATA / "gu_lexicon.tsv"
    lex_lines = [f"{gu}\t{roman}\t{w}" for roman, (gu, w) in sorted(lexicon.items(), key=lambda x: x[0])]
    lex_path.write_text("\n".join(lex_lines) + "\n", encoding="utf-8")
    print(f"lexicon: {len(lex_lines)} -> {lex_path}")

    # Compact JSON for qjs: roman → gujarati + weights for general ranking
    trie_blob = {
        "exceptions": exceptions,
        "lexicon": {r: gu for r, (gu, _w) in lexicon.items()},
        "weights": {r: int(w) for r, (_gu, w) in lexicon.items()},
        "sp_words": sp_words[:8000],
    }
    blob_path = DATA / "gu_lexicon_blob.json"
    blob_path.write_text(json.dumps(trie_blob, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"lexicon blob: {blob_path} ({blob_path.stat().st_size} bytes)")

    # Rime dict yaml
    dict_yaml = RIME_OUT / "gujarati_apple.dict.yaml"
    body = ["# Apple-distilled Gujarati lexicon", "---", "name: gujarati_apple", 'version: "1.0"', "sort: by_weight", "...", ""]
    for roman, (gu, w) in sorted(lexicon.items(), key=lambda x: (-x[1][1], x[0])):
        body.append(f"{gu}\t{roman}\t{w}")
    dict_yaml.write_text("\n".join(body) + "\n", encoding="utf-8")
    print(f"rime dict: {dict_yaml}")

    # Training jsonl from Apple ranked lists
    train_path = DATA / "gu_train.jsonl"
    with train_path.open("w", encoding="utf-8") as fh:
        for inp, cands in sorted(by_input.items()):
            # dedupe preserving order
            seen = set()
            ordered = []
            for gu, typ, lm in cands:
                if gu in seen:
                    continue
                seen.add(gu)
                ordered.append({"text": gu, "type": typ, "lm": lm})
            if not ordered:
                continue
            row = {
                "input": inp,
                "candidates": ordered,
                "label": 0,  # top Apple candidate is positive
            }
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            # also emit pairwise positives
            train_rows.append(row)
    print(f"train jsonl: {len(train_rows)} -> {train_path}")

    # Copy blob next to rime package
    (RIME_OUT / "gu_lexicon_blob.json").write_text(blob_path.read_text(encoding="utf-8"), encoding="utf-8")
    (RIME_OUT / "gu_phonetic_rules.json").write_bytes((DATA / "gu_phonetic_rules.json").read_bytes())
    (RIME_OUT / "gu_exceptions.tsv").write_bytes(exc_path.read_bytes())
    (RIME_OUT / "gu_lexicon.tsv").write_bytes(lex_path.read_bytes())


if __name__ == "__main__":
    distill_all()
