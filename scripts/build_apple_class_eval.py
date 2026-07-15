#!/usr/bin/env python3
"""Build deterministic source-disjoint Apple-class accuracy fixtures from open corpora."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "splits" / "apple_class_source_disjoint.jsonl"
MANIFEST = ROOT / "data" / "splits" / "apple_class_source_disjoint_meta.json"
SHORT_OUT = ROOT / "data" / "splits" / "apple_class_short_behavior.jsonl"
SOURCES = {
    "aksharantar": ROOT / "data" / "external" / "aksharantar_gu_pairs.tsv",
    "dakshina": ROOT / "data" / "external" / "dakshina_gu_pairs.tsv",
}


def roman_family(value: str) -> str:
    value = re.sub(r"[^a-z+]", "", value.lower())
    return re.sub(r"([aeiou])\1+", r"\1", value)


def stable_key(source: str, roman: str, native: str) -> str:
    return hashlib.sha256(f"apple-class-v1\t{source}\t{roman}\t{native}".encode()).hexdigest()


def main() -> int:
    blob = json.loads((ROOT / "rime" / "js" / "gu_lexicon_blob.json").read_text(encoding="utf-8"))
    runtime = blob.get("lexicon") or {}
    runtime_families = {roman_family(key) for key in runtime}
    runtime_natives = {unicodedata.normalize("NFC", str(native)) for native in runtime.values()}
    selected: list[dict] = []
    counts = {}
    for source, path in SOURCES.items():
        candidates: dict[tuple[str, str], dict] = {}
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            roman = parts[0].strip().lower()
            native = unicodedata.normalize("NFC", parts[1].strip())
            if not roman or not native or roman_family(roman) in runtime_families or native in runtime_natives:
                continue
            if not all("\u0A80" <= ch <= "\u0AFF" or ch in "\u200c\u200d" for ch in native):
                continue
            row = {"roman": roman, "native": native, "source": source, "length_band": "1-3" if len(roman) <= 3 else "4-6" if len(roman) <= 6 else "7-9" if len(roman) <= 9 else "10-14" if len(roman) <= 14 else "15+"}
            candidates[(roman, native)] = row
        ordered = sorted(candidates.values(), key=lambda row: stable_key(source, row["roman"], row["native"]))
        take = ordered[:10_000]
        selected.extend(take)
        counts[source] = {"eligible": len(ordered), "selected": len(take)}
    selected.sort(key=lambda row: (row["source"], stable_key(row["source"], row["roman"], row["native"])))
    OUT.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in selected), encoding="utf-8")
    weights = blob.get("weights") or {}
    short_rows = []
    for roman, native in runtime.items():
        if not 1 <= len(roman) <= 3 or not native:
            continue
        short_rows.append({"roman": roman, "acceptable": [native], "kind": "runtime_behavior", "weight": float(weights.get(roman) or 0)})
    short_rows.sort(key=lambda row: (-row["weight"], stable_key("short", row["roman"], row["acceptable"][0])))
    short_rows = short_rows[:500]
    SHORT_OUT.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in short_rows), encoding="utf-8")
    bands: dict[str, int] = defaultdict(int)
    for row in selected:
        bands[row["length_band"]] += 1
    manifest = {"version": 1, "seed": "apple-class-v1", "runtime_roman_families_excluded": len(runtime_families), "runtime_natives_excluded": len(runtime_natives), "sources": counts, "selected": len(selected), "length_bands": dict(sorted(bands.items())), "short_behavior_cases": len(short_rows)}
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if all(info["selected"] == 10_000 for info in counts.values()) and len(short_rows) == 500 else 1


if __name__ == "__main__":
    raise SystemExit(main())
