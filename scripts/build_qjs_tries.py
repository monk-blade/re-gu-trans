#!/usr/bin/env python3
"""Build compact trie text + optional native-compatible .bin Tries for librime-qjs.

Text outputs (build inputs / offline fallback):
  lexicon.trie.txt, prefix.trie.txt, native_lm.tsv

Binary outputs (runtime hot path; platform size_t native endian):
  lexicon.trie.bin, prefix.trie.bin, native_lm.trie.bin

Binary layout matches HuangJian/librime-qjs Trie::saveToBinaryFile:
  size_t n; n×(size_t len + utf8 bytes); size_t marisa_size; marisa blob
Uses marisa_trie with binary=True (MARISA_BINARY_TAIL).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
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
OUT_LEX_BIN = JS / "lexicon.trie.bin"
OUT_PFX_BIN = JS / "prefix.trie.bin"
OUT_NAT_BIN = JS / "native_lm.trie.bin"
OUT_NAT_META = JS / "native_lm_meta.json"
EXCEPTIONS_OUT = JS / "exceptions.json"
STRONG = 100
PREFIX_MAX = 8
SEP = "\x1e"  # multi-value concat for prefix collisions (matches Concat option spirit)


def write_text_assets(lex: dict, weights: dict):
    lines = []
    for roman, native in sorted(lex.items()):
        w = float(weights.get(roman, STRONG) or STRONG)
        soft = 1 if 0 < w < STRONG else 0
        lines.append(f"{roman}\t{native}\x1f{int(w)}\x1f{soft}")
    OUT_LEX.write_text("\n".join(lines) + "\n", encoding="utf-8")

    buckets: dict[str, list[tuple[float, str, str]]] = defaultdict(list)
    for roman, native in lex.items():
        w = float(weights.get(roman, STRONG) or STRONG)
        for n in range(2, min(7, len(roman) + 1)):
            buckets[roman[:n]].append((w, roman, native))
    pfx_lines = []
    pfx_map: dict[str, str] = {}
    for prefix, items in sorted(buckets.items()):
        items.sort(key=lambda x: -x[0])
        parts = []
        for w, roman, native in items[:PREFIX_MAX]:
            payload = f"{native}\x1f{int(w)}\x1f{roman}"
            pfx_lines.append(f"{prefix}\t{payload}")
            parts.append(payload)
        pfx_map[prefix] = SEP.join(parts)
    OUT_PFX.write_text("\n".join(pfx_lines) + "\n", encoding="utf-8")

    uni: dict[str, int] = {}
    if UNI.exists():
        for line in UNI.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) >= 2 and parts[1].isdigit():
                uni[parts[0]] = int(parts[1])
    stems: dict[str, int] = {}
    if STEMS.exists():
        stems = {
            k: int(v)
            for k, v in json.loads(STEMS.read_text()).items()
            if str(v).isdigit() or isinstance(v, (int, float))
        }
    attested: set[str] = set()
    attested_floor = 50
    if ATT.exists():
        data = json.loads(ATT.read_text())
        words = data.get("words") if isinstance(data, dict) else data
        if isinstance(words, list):
            attested = set(map(str, words))
        elif isinstance(words, dict):
            attested = set(words)
        if isinstance(data, dict) and str(data.get("floor", "")).isdigit():
            attested_floor = int(data["floor"])

    natives = set(lex.values()) | set(uni) | set(stems) | attested
    nat_lines = []
    nat_map: dict[str, str] = {}
    for w in sorted(natives):
        if not w:
            continue
        payload = f"{uni.get(w, 0)}\t{stems.get(w, 0)}\t{1 if w in attested else 0}"
        nat_lines.append(f"{w}\t{payload}")
        nat_map[w] = payload
    OUT_NAT.write_text("\n".join(nat_lines) + "\n", encoding="utf-8")
    metadata = {
        "version": 1,
        "payload_format": "unigram\\tstem\\tattested",
        "max_unigram": max(uni.values(), default=1),
        "attested_floor": attested_floor,
        "native_count": len(nat_map),
    }
    OUT_NAT_META.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(lines), len(pfx_lines), len(nat_lines), pfx_map, nat_map  # type: ignore


def write_qjs_trie_bin(path: Path, mapping: dict[str, str]) -> None:
    try:
        import marisa_trie
    except ImportError as e:
        raise SystemExit(
            "marisa-trie required for --bin (pip install marisa-trie). " + str(e)
        ) from e

    keys = list(mapping.keys())
    if not keys:
        path.write_bytes(struct.pack("N", 0) + struct.pack("N", 0))
        return
    trie = marisa_trie.Trie(keys, binary=True)
    data = [""] * len(keys)
    for k, v in mapping.items():
        data[trie.key_id(k)] = v
    marisa_bytes = trie.tobytes()

    def write_sized(f, s: str) -> None:
        b = s.encode("utf-8")
        f.write(struct.pack("N", len(b)))
        f.write(b)

    with path.open("wb") as f:
        f.write(struct.pack("N", len(data)))
        for s in data:
            write_sized(f, s)
        f.write(struct.pack("N", len(marisa_bytes)))
        f.write(marisa_bytes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", action="store_true", help="Also emit platform .trie.bin files")
    ap.add_argument("--exceptions", action="store_true", help="Write small exceptions.json")
    args = ap.parse_args()

    blob = json.loads(BLOB.read_text(encoding="utf-8"))
    lex = blob.get("lexicon") or {}
    weights = blob.get("weights") or {}
    exceptions = blob.get("exceptions") or {}

    n_lex, n_pfx, n_nat, pfx_map, nat_map = write_text_assets(lex, weights)
    print(f"wrote {OUT_LEX} ({n_lex} keys)")
    print(f"wrote {OUT_PFX} ({n_pfx} prefix rows)")
    print(f"wrote {OUT_NAT} ({n_nat} natives)")
    print(f"wrote {OUT_NAT_META}")

    if args.exceptions or args.bin:
        EXCEPTIONS_OUT.write_text(
            json.dumps({"exceptions": exceptions}, ensure_ascii=False, indent=0) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {EXCEPTIONS_OUT} ({len(exceptions)} exceptions)")

    if args.bin:
        lex_map = {
            roman: f"{native}\x1f{int(float(weights.get(roman, STRONG) or STRONG))}"
            f"\x1f{1 if 0 < float(weights.get(roman, STRONG) or STRONG) < STRONG else 0}"
            for roman, native in lex.items()
        }
        write_qjs_trie_bin(OUT_LEX_BIN, lex_map)
        write_qjs_trie_bin(OUT_PFX_BIN, pfx_map)
        write_qjs_trie_bin(OUT_NAT_BIN, nat_map)
        print(f"wrote {OUT_LEX_BIN} ({OUT_LEX_BIN.stat().st_size} bytes)")
        print(f"wrote {OUT_PFX_BIN} ({OUT_PFX_BIN.stat().st_size} bytes)")
        print(f"wrote {OUT_NAT_BIN} ({OUT_NAT_BIN.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
