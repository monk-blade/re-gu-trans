#!/usr/bin/env python3
"""Build rime/js/emoji_keywords.json from a Rime-style emoji dict.yaml.

Default source: ~/Library/Rime/gujarati_emoji.dict.yaml if present, else
data/gujarati_emoji.dict.yaml.

Output shape: { "smile": [{"e": "🙂", "w": 1000}, ...], ... }
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "rime" / "js" / "emoji_keywords.json"


def find_source() -> Path:
    candidates = [
        ROOT / "data" / "gujarati_emoji.dict.yaml",
        ROOT / "rime" / "gujarati_emoji.dict.yaml",
        Path.home() / "Library/Rime/gujarati_emoji.dict.yaml",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise SystemExit(f"No emoji dict found. Tried: {', '.join(str(p) for p in candidates)}")


def parse_dict(path: Path) -> dict[str, list[dict]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    body = text.split("...", 1)[-1]
    by_code: dict[str, list[dict]] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for line in body.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        parts = raw.rsplit(None, 2)
        if len(parts) != 3 or not parts[2].isdigit():
            continue
        emoji, code, weight_s = parts[0].strip(), parts[1].lower(), parts[2]
        if not emoji or not all(("a" <= c <= "z") or c in "'-" for c in code):
            continue
        key = (code, emoji)
        if key in seen:
            continue
        seen.add(key)
        by_code[code].append({"e": emoji, "w": int(weight_s)})

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
        out[code] = dedup
    return out


def main() -> None:
    src = find_source()
    data = parse_dict(src)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {OUT} from {src} codes={len(data)} pairs={sum(len(v) for v in data.values())}")


if __name__ == "__main__":
    main()
