#!/usr/bin/env python3
"""Build compact trie text assets for qjs Trie.loadTextFile / lightweight loaders.

Outputs under rime/js/:
  lexicon.trie.txt   — roman\\tnative\\x1fweight\\x1fsoft
  prefix.trie.txt    — prefix\\tnative\\x1fweight (short pre-ranked lists, top per prefix)
  native_lm.tsv      — native\\tunigram\\tstem\\tattested

Does not require Apple private dumps. Uses gu_lexicon_blob.json + LM files.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "rime" / "js"
BLOB = JS / "gu_lexicon_blob.json"
UNI = JS / "lm" / "unigram.tsv"
STEMS = JS / "lm" / "stems.json"
ATT = JS / "lm" / "attested.json"
OUT_LEX = JS / "lexicon.trie.txt"
OUT_PFX = JS / "prefix.trie.txt"
OUT_NAT = JS / "native_lm.tsv"
STRONG = 100
PREFIX_MAX = 8


def main() -> int:
    blob = json.loads(BLOB.read_text(encoding="utf-8"))
    lex = blob.get("lexicon") or {}
    weights = blob.get("weights") or {}

    lines = []
    for roman, native in sorted(lex.items()):
        w = float(weights.get(roman, STRONG) or STRONG)
        soft = 1 if 0 < w < STRONG else 0
        # value payload for trie/text loaders
        lines.append(f"{roman}\t{native}\x1f{int(w)}\x1f{soft}")
    OUT_LEX.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Prefix shortlists: for each prefix length 2..min(6,len), keep top PREFIX_MAX by weight
    buckets: dict[str, list[tuple[float, str, str]]] = defaultdict(list)
    for roman, native in lex.items():
        w = float(weights.get(roman, STRONG) or STRONG)
        for n in range(2, min(7, len(roman) + 1)):
            buckets[roman[:n]].append((w, roman, native))
    pfx_lines = []
    for prefix, items in sorted(buckets.items()):
        items.sort(key=lambda x: -x[0])
        for w, roman, native in items[:PREFIX_MAX]:
            pfx_lines.append(f"{prefix}\t{native}\x1f{int(w)}\x1f{roman}")
    OUT_PFX.write_text("\n".join(pfx_lines) + "\n", encoding="utf-8")

    uni: dict[str, int] = {}
    if UNI.exists():
        for line in UNI.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].isdigit():
                uni[parts[0]] = int(parts[1])
    stems: dict[str, int] = {}
    if STEMS.exists():
        stems = {k: int(v) for k, v in json.loads(STEMS.read_text()).items() if str(v).isdigit() or isinstance(v, (int, float))}
    attested: set[str] = set()
    if ATT.exists():
        data = json.loads(ATT.read_text())
        words = data.get("words") if isinstance(data, dict) else data
        if isinstance(words, list):
            attested = set(map(str, words))
        elif isinstance(words, dict):
            attested = set(words)

    natives = set(lex.values()) | set(uni) | set(stems) | attested
    nat_lines = []
    for w in sorted(natives):
        if not w:
            continue
        nat_lines.append(
            f"{w}\t{uni.get(w, 0)}\t{stems.get(w, 0)}\t{1 if w in attested else 0}"
        )
    OUT_NAT.write_text("\n".join(nat_lines) + "\n", encoding="utf-8")

    print(f"wrote {OUT_LEX} ({len(lines)} keys)")
    print(f"wrote {OUT_PFX} ({len(pfx_lines)} prefix rows)")
    print(f"wrote {OUT_NAT} ({len(nat_lines)} natives)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
