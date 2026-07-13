#!/usr/bin/env python3
"""Extract Gujarati natives from local proprietary IME assets (never committed).

Apple:
  - gu_unified_marisa_keys.txt (repo root, gitignored)
  - data/apple_probe.tsv, data/gu_lexicon.tsv, rime/gu_lexicon_blob.json

Google Input Tools:
  - Env GOOGLE_IME_GU_DICT or data/external/google_ime_gu.*
  - Accepts .txt / .tsv / .csv wordlists (native or roman\\tnative)

Writes (gitignored under data/external/):
  apple_native_words.txt
  google_ime_native_words.txt

Missing assets → warn and skip (CI / non-Mac OK).
"""
from __future__ import annotations

import csv
import json
import os
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EXT = DATA / "external"

GU_RE = re.compile(r"[\u0A80-\u0AFF]+")


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())


def is_gujarati_word(w: str) -> bool:
    return bool(w) and any("\u0A80" <= ch <= "\u0AFF" for ch in w) and len(w) >= 2


def extract_gu_tokens(text: str) -> set[str]:
    out: set[str] = set()
    for m in GU_RE.finditer(text):
        w = nfc(m.group(0))
        if is_gujarati_word(w):
            out.add(w)
    return out


def load_lines_gu(path: Path) -> set[str]:
    out: set[str] = set()
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        out |= extract_gu_tokens(line)
        # also whole-line if pure GU
        w = nfc(line.split("\t")[0] if "\t" in line else line)
        if is_gujarati_word(w) and not any(c.isascii() and c.isalpha() for c in w):
            out.add(w)
    return out


def extract_apple() -> set[str]:
    out: set[str] = set()
    candidates = [
        ROOT / "gu_unified_marisa_keys.txt",
        DATA / "apple_probe.tsv",
        DATA / "gu_lexicon.tsv",
        DATA / "gu_lexicon_blob.json",
        ROOT / "rime" / "gu_lexicon_blob.json",
        EXT / "apple_native_words.txt",
    ]
    found_any = False
    for path in candidates:
        if not path.exists():
            continue
        found_any = True
        if path.suffix == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for gu in (data.get("lexicon") or {}).values():
                    gu = nfc(str(gu))
                    if is_gujarati_word(gu):
                        out.add(gu)
            except Exception as e:
                print(f"WARN: apple json {path}: {e}")
            continue
        # TSV probe: roman\\tgu\\t...
        if path.suffix == ".tsv" or path.name.endswith(".tsv"):
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and is_gujarati_word(nfc(parts[1])):
                    out.add(nfc(parts[1]))
                elif len(parts) >= 1 and is_gujarati_word(nfc(parts[0])):
                    out.add(nfc(parts[0]))
            continue
        out |= load_lines_gu(path)
    if not found_any:
        print("WARN: no Apple proprietary/local lexicon sources found; skip T0 extra natives")
    return out


def find_google_ime_paths() -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get("GOOGLE_IME_GU_DICT", "").strip()
    if env:
        paths.append(Path(env).expanduser())
    for p in sorted(EXT.glob("google_ime_gu*")):
        paths.append(p)
    return [p for p in paths if p.exists() and p.is_file()]


def extract_google_ime() -> set[str]:
    out: set[str] = set()
    paths = find_google_ime_paths()
    if not paths:
        print(
            "WARN: no Google Input Tools dict found. Place at data/external/google_ime_gu.txt "
            "or set GOOGLE_IME_GU_DICT=/path/to/dump (gitignored). Skip T0b."
        )
        return out
    for path in paths:
        print(f"parse Google IME dict {path}")
        text = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix.lower() in {".csv"}:
            try:
                for row in csv.reader(text.splitlines()):
                    for cell in row:
                        out |= extract_gu_tokens(cell)
            except Exception:
                out |= extract_gu_tokens(text)
        else:
            for line in text.splitlines():
                parts = line.split("\t")
                # prefer native column if present
                if len(parts) >= 2 and is_gujarati_word(nfc(parts[1])):
                    out.add(nfc(parts[1]))
                elif len(parts) >= 1 and is_gujarati_word(nfc(parts[0])):
                    out.add(nfc(parts[0]))
                else:
                    out |= extract_gu_tokens(line)
    return out


def write_words(path: Path, words: set[str]) -> None:
    EXT.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(sorted(words)) + ("\n" if words else ""), encoding="utf-8")
    print(f"wrote {path} ({len(words)})")


def main() -> None:
    EXT.mkdir(parents=True, exist_ok=True)
    apple = extract_apple()
    write_words(EXT / "apple_native_words.txt", apple)
    git = extract_google_ime()
    write_words(EXT / "google_ime_native_words.txt", git)
    print(f"done apple={len(apple)} google_ime={len(git)}")


if __name__ == "__main__":
    main()
