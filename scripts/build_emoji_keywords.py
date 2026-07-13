#!/usr/bin/env python3
"""Build rime/js/emoji_keywords.json from local GU dict + GitHub EN/CLDR sources.

Sources (merged, roman/latin codes only — Rime speller is ASCII):
  1. data/gujarati_emoji.dict.yaml  — curated EN + Gujarati-roman (high weight)
  2. muan/emojilib emoji-en-US.json — large English keyword set (MIT)
  3. unicode-org/cldr-json annotations/en — CLDR English keywords (Unicode)
  4. Optional: data/emoji_gu_roman_extra.tsv — extra GU-roman\\temoji lines

CLDR Gujarati annotations are native-script (not typeable in this IME); GU coverage
comes from the curated dict + extra TSV. English CLDR/emojilib expand EN triggers.

Output: { "smile": [{"e": "🙂", "w": 1000}, ...], ... }
"""
from __future__ import annotations

import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "rime" / "js" / "emoji_keywords.json"
EXT = ROOT / "data" / "external"
CACHE = EXT / "emoji"

EMOJILIB_URL = "https://raw.githubusercontent.com/muan/emojilib/main/dist/emoji-en-US.json"
CLDR_EN_URL = (
    "https://raw.githubusercontent.com/unicode-org/cldr-json/main/"
    "cldr-json/cldr-annotations-full/annotations/en/annotations.json"
)

# Weight bands: curated GU/EN dict > emojilib > CLDR
W_CURATED = 1000
W_EMOJILIB = 700
W_CLDR = 500

CODE_OK = re.compile(r"^[a-z][a-z0-9'-]{0,31}$")


def nfc_code(raw: str) -> str | None:
    s = raw.strip().lower().replace("_", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9'\s-]", "", s)
    s = re.sub(r"\s+", "", s)  # smile face → smileface; also keep single tokens separately
    if not s or not CODE_OK.match(s):
        return None
    return s


def token_codes(phrase: str) -> list[str]:
    """Emit joined phrase + individual ascii tokens suitable as IME codes."""
    out: list[str] = []
    raw = phrase.strip().lower()
    joined = nfc_code(raw)
    if joined:
        out.append(joined)
    for part in re.split(r"[\s_/|+-]+", raw):
        c = nfc_code(part)
        if c and c not in out and len(c) >= 2:
            out.append(c)
    return out


def fetch(url: str, cache: Path) -> str:
    if cache.exists() and cache.stat().st_size > 200:
        return cache.read_text(encoding="utf-8", errors="ignore")
    print(f"fetch {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 re-gu-trans-emoji"})
    with urllib.request.urlopen(req, timeout=90) as resp:
        text = resp.read().decode("utf-8", errors="ignore")
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    return text


def add(by_code: dict[str, list[dict]], seen: set[tuple[str, str]], code: str, emoji: str, weight: int) -> None:
    if not code or not emoji:
        return
    key = (code, emoji)
    if key in seen:
        return
    seen.add(key)
    by_code[code].append({"e": emoji, "w": weight})


def parse_local_dict(path: Path, by_code: dict, seen: set) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    body = text.split("...", 1)[-1]
    n = 0
    for line in body.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        parts = raw.rsplit(None, 2)
        if len(parts) != 3 or not parts[2].isdigit():
            continue
        emoji, code, weight_s = parts[0].strip(), parts[1].lower(), parts[2]
        if not emoji or not CODE_OK.match(code):
            continue
        add(by_code, seen, code, emoji, max(int(weight_s), W_CURATED))
        n += 1
    return n


def parse_extra_tsv(path: Path, by_code: dict, seen: set) -> int:
    if not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        parts = raw.split("\t")
        if len(parts) < 2:
            continue
        code, emoji = parts[0].lower().strip(), parts[1].strip()
        w = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else W_CURATED
        if CODE_OK.match(code):
            add(by_code, seen, code, emoji, w)
            n += 1
    return n


def merge_emojilib(by_code: dict, seen: set) -> int:
    text = fetch(EMOJILIB_URL, CACHE / "emojilib-en-US.json")
    data = json.loads(text)
    n = 0
    for emoji, keywords in data.items():
        if not isinstance(keywords, list):
            continue
        for kw in keywords:
            if not isinstance(kw, str):
                continue
            # skip :shortcode: style with colons only
            kw = kw.strip(":")
            for code in token_codes(kw):
                add(by_code, seen, code, emoji, W_EMOJILIB)
                n += 1
    return n


def merge_cldr_en(by_code: dict, seen: set) -> int:
    text = fetch(CLDR_EN_URL, CACHE / "cldr-en-annotations.json")
    data = json.loads(text)
    annotations = data.get("annotations", {}).get("annotations") or {}
    n = 0
    for emoji, meta in annotations.items():
        if not isinstance(meta, dict):
            continue
        words = list(meta.get("default") or [])
        tts = meta.get("tts")
        if isinstance(tts, list):
            words.extend(tts)
        elif isinstance(tts, str):
            words.append(tts)
        for kw in words:
            if not isinstance(kw, str):
                continue
            for code in token_codes(kw):
                add(by_code, seen, code, emoji, W_CLDR)
                n += 1
    return n


def find_local_dict() -> Path | None:
    for p in (
        ROOT / "data" / "gujarati_emoji.dict.yaml",
        ROOT / "rime" / "gujarati_emoji.dict.yaml",
        Path.home() / "Library/Rime/gujarati_emoji.dict.yaml",
    ):
        if p.exists():
            return p
    return None


def finalize(by_code: dict[str, list[dict]]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for code, items in sorted(by_code.items()):
        items.sort(key=lambda x: -x["w"])
        dedup: list[dict] = []
        seen_e: set[str] = set()
        for it in items:
            if it["e"] in seen_e:
                continue
            seen_e.add(it["e"])
            dedup.append(it)
            if len(dedup) >= 6:  # cap emojis per keyword
                break
        out[code] = dedup
    return out


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    by_code: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()

    local = find_local_dict()
    n_local = parse_local_dict(local, by_code, seen) if local else 0
    n_extra = parse_extra_tsv(ROOT / "data" / "emoji_gu_roman_extra.tsv", by_code, seen)
    n_lib = merge_emojilib(by_code, seen)
    n_cldr = merge_cldr_en(by_code, seen)

    out = finalize(by_code)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT} codes={len(out)} pairs={sum(len(v) for v in out.values())} "
        f"(local={n_local} gu_extra={n_extra} emojilib={n_lib} cldr_en={n_cldr})"
    )


if __name__ == "__main__":
    main()
