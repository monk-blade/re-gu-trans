#!/usr/bin/env python3
"""Extract Gujarati natives from local proprietary IME assets (never committed).

Apple:
  - archive/apple-extracts/gu_unified_marisa_keys.txt (or repo root; gitignored)
  - data/apple_probe.tsv, data/gu_lexicon.tsv, rime/js/gu_lexicon_blob.json

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
        ROOT / "archive" / "apple-extracts" / "gu_unified_marisa_keys.txt",
        ROOT / "gu_unified_marisa_keys.txt",
        DATA / "apple_probe.tsv",
        DATA / "gu_lexicon.tsv",
        DATA / "gu_lexicon_blob.json",
        ROOT / "rime" / "js" / "gu_lexicon_blob.json",
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
    if paths:
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
                    if len(parts) >= 2 and is_gujarati_word(nfc(parts[1])):
                        out.add(nfc(parts[1]))
                    elif len(parts) >= 1 and is_gujarati_word(nfc(parts[0])):
                        out.add(nfc(parts[0]))
                    else:
                        out |= extract_gu_tokens(line)
        return out

    # Fallback (frost/ice pattern): high-count Google i18n GU wordcounts as T0b natives
    # when proprietary Input Tools dump is unavailable. Roman→native soft pairs still need
    # google_ime_gu.* or GOOGLE_IME_GU_DICT.
    wc = EXT / "gu_google_wordcounts.txt"
    if not wc.exists():
        print(
            "WARN: no Google Input Tools dict found. Place at data/external/google_ime_gu.txt "
            "or set GOOGLE_IME_GU_DICT=/path/to/dump (gitignored). Skip T0b."
        )
        return out
    print(f"fallback: Google wordcounts natives from {wc}")
    for line in wc.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = [p.strip() for p in line.split("\t") if p.strip()]
        if len(parts) < 2:
            continue
        # Accept count\\tword (i18n dumps) or word\\tcount.
        w_raw, c_raw = parts[0], parts[1]
        if is_gujarati_word(nfc(w_raw)):
            w, c_s = nfc(w_raw), c_raw
        elif is_gujarati_word(nfc(c_raw)):
            w, c_s = nfc(c_raw), w_raw
        else:
            continue
        try:
            c = int(float(c_s))
        except ValueError:
            continue
        if c >= 20 and len(w) <= 20:
            out.add(w)
    print(f"google wordcount natives={len(out)}")
    return out


def soft_fill_google_pairs() -> int:
    """Optional roman\\tnative soft-fill from google_ime_gu.* (never override Apple)."""
    blob_path = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
    if not blob_path.exists():
        return 0
    paths = find_google_ime_paths()
    pairs: dict[str, str] = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = [p.strip() for p in line.split("\t")]
            if len(parts) < 2:
                continue
            a, b = parts[0], parts[1]
            if is_gujarati_word(nfc(a)) and all(c.isalpha() or c in ".'-" for c in b.lower()) and len(b) >= 2:
                pairs[b.lower()] = nfc(a)
            elif is_gujarati_word(nfc(b)) and all(c.isalpha() or c in ".'-" for c in a.lower()) and len(a) >= 2:
                pairs[a.lower()] = nfc(b)
    if not pairs:
        return 0
    blob = json.loads(blob_path.read_text(encoding="utf-8"))
    lex = blob.setdefault("lexicon", {})
    weights = blob.setdefault("weights", {})
    native_set = set(lex.values())
    added = 0
    for roman, native in sorted(pairs.items(), key=lambda x: (len(x[0]), x[0])):
        if roman in lex:
            continue
        if len(native) > 16 or " " in native:
            continue
        # skip postfix when stem known
        for pf in ("માં", "ની", "ના", "ને", "નો", "નું", "થી"):
            if native.endswith(pf) and native[: -len(pf)] in native_set:
                break
        else:
            lex[roman] = native
            weights[roman] = 80  # soft mid band
            native_set.add(native)
            added += 1
            if added >= 40_000:
                break
    if added:
        blob["google_ime_soft_added"] = added
        blob_path.write_text(json.dumps(blob, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        (DATA / "gu_lexicon_blob.json").write_bytes(blob_path.read_bytes())
        print(f"google_ime soft roman pairs added={added}")
    return added


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
    soft_fill_google_pairs()
    print(f"done apple={len(apple)} google_ime={len(git)}")


if __name__ == "__main__":
    main()
