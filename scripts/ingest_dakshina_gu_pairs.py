#!/usr/bin/env python3
"""Soft-fill bare-stem roman→native from Dakshina GU translit lexicons.

Never overrides Apple / existing keys (weight ≥100). Soft weights stay <100.
Skips postfix natives when the stem is already in the lexicon (runtime stem_postfix).

Source (local cache under data/external/):
  dakshina_dataset_v1.0.tar → gu/lexicons/gu.translit.sampled.*.tsv
  Format: native\\troman\\tcount
"""
from __future__ import annotations

import argparse
import json
import tarfile
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
EXT = DATA / "external"
BLOB_PATH = ROOT / "rime" / "js" / "gu_lexicon_blob.json"
TAR = EXT / "dakshina_dataset_v1.0.tar"
OUT_PAIRS = EXT / "dakshina_gu_pairs.tsv"
OUT_NATIVE = EXT / "dakshina_gu_natives.txt"
TEST_SPLIT = DATA / "splits" / "test_romans.json"

SOFT_WEIGHT = 75
SOFT_WEIGHT_MID = 80
SOFT_WEIGHT_HIGH = 85
MAX_SOFT_ADD = 80_000

GU_POSTFIXES = [
    "માંથી",
    "વાળું",
    "વાળી",
    "વાળા",
    "વાળો",
    "માં",
    "થી",
    "ની",
    "નું",
    "નાં",
    "ના",
    "ને",
    "નો",
]


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())


def is_gujarati(w: str) -> bool:
    return bool(w) and any("\u0A80" <= ch <= "\u0AFF" for ch in w)


def is_roman(w: str) -> bool:
    if not w or len(w) > 32 or len(w) < 2:
        return False
    return all(("a" <= c <= "z") or c in ".'-" for c in w.lower()) and any(c.isalpha() for c in w)


def strip_postfix(gu: str) -> str | None:
    for pf in GU_POSTFIXES:
        if gu.endswith(pf) and len(gu) > len(pf) + 1:
            return gu[: -len(pf)]
    return None


def soft_weight_for_count(cnt: int) -> int:
    # Dakshina sampled counts top out ~7; calibrate mid/high to that range.
    if cnt >= 5:
        return SOFT_WEIGHT_HIGH
    if cnt >= 3:
        return SOFT_WEIGHT_MID
    return SOFT_WEIGHT


def is_soft_weight(w: float | int) -> bool:
    try:
        v = float(w)
    except (TypeError, ValueError):
        return False
    return 0 < v < 100


def load_pairs_from_tar(tar_path: Path) -> dict[str, tuple[str, int]]:
    """roman → (native, count) preferring highest count."""
    pair_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    members = [
        "dakshina_dataset_v1.0/gu/lexicons/gu.translit.sampled.train.tsv",
        "dakshina_dataset_v1.0/gu/lexicons/gu.translit.sampled.dev.tsv",
        "dakshina_dataset_v1.0/gu/lexicons/gu.translit.sampled.test.tsv",
    ]
    with tarfile.open(tar_path, "r") as tf:
        for name in members:
            try:
                fh = tf.extractfile(name)
            except KeyError:
                continue
            if fh is None:
                continue
            for raw in fh.read().decode("utf-8", errors="ignore").splitlines():
                parts = raw.split("\t")
                if len(parts) < 2:
                    continue
                native, roman = nfc(parts[0]), parts[1].strip().lower()
                cnt = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 1
                if not is_gujarati(native) or not is_roman(roman):
                    continue
                pair_counts[roman][native] += cnt
    best: dict[str, tuple[str, int]] = {}
    for roman, choices in pair_counts.items():
        native, cnt = max(choices.items(), key=lambda x: x[1])
        best[roman] = (native, cnt)
    return best


def merge_soft(
    best: dict[str, tuple[str, int]],
    max_add: int,
    soft_cap: int = 300_000,
    exclude_romans: set[str] | None = None,
) -> dict:
    path = BLOB_PATH
    blob = json.loads(path.read_text(encoding="utf-8"))
    lex: dict = blob.setdefault("lexicon", {})
    weights: dict = blob.setdefault("weights", {})
    native_set = set(lex.values())
    soft_count = sum(1 for w in weights.values() if is_soft_weight(w))
    blocked = {r.lower() for r in (exclude_romans or set())}
    added = 0
    upgraded = 0
    skipped_pf = 0
    skipped_exist = 0
    skipped_test = 0

    # Pass 1 — upgrade soft bands even when already at soft_cap.
    for roman, (native, cnt) in best.items():
        if roman in blocked:
            continue
        if roman not in lex:
            continue
        cur = float(weights.get(roman, 0) or 0)
        if is_soft_weight(cur) and lex.get(roman) == native:
            nw = soft_weight_for_count(cnt)
            if nw > cur:
                weights[roman] = nw
                upgraded += 1

    ranked = sorted(
        best.items(),
        key=lambda x: (0 if strip_postfix(x[1][0]) is None else 1, -x[1][1], x[0]),
    )
    for roman, (native, cnt) in ranked:
        if added >= max_add or soft_count >= soft_cap:
            break
        if roman in blocked:
            skipped_test += 1
            continue
        if roman in lex:
            skipped_exist += 1
            continue
        stem = strip_postfix(native)
        if stem and stem in native_set:
            skipped_pf += 1
            continue
        if stem is not None:
            # Dakshina: skip postfix morphs entirely (stem_postfix synthesizes).
            skipped_pf += 1
            continue
        if " " in native or len(native) > 16:
            continue
        lex[roman] = native
        weights[roman] = soft_weight_for_count(cnt)
        native_set.add(native)
        soft_count += 1
        added += 1

    blob["lexicon"] = lex
    blob["weights"] = weights
    blob["dakshina_soft_added"] = added
    blob["dakshina_soft_upgraded"] = upgraded
    out = json.dumps(blob, ensure_ascii=False, separators=(",", ":"))
    BLOB_PATH.parent.mkdir(parents=True, exist_ok=True)
    BLOB_PATH.write_text(out, encoding="utf-8")
    (DATA / "gu_lexicon_blob.json").write_text(out, encoding="utf-8")
    return {
        "added": added,
        "upgraded": upgraded,
        "skipped_postfix": skipped_pf,
        "skipped_existing": skipped_exist,
        "skipped_test": skipped_test,
        "pairs": len(best),
        "max_add": max_add,
        "soft_total": soft_count,
        "soft_cap": soft_cap,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-add", type=int, default=MAX_SOFT_ADD)
    ap.add_argument("--soft-cap", type=int, default=300_000, help="Global soft-key ceiling")
    ap.add_argument("--from-cache", action="store_true", help="Use dakshina_gu_pairs.tsv if present")
    args = ap.parse_args()

    EXT.mkdir(parents=True, exist_ok=True)
    best: dict[str, tuple[str, int]] = {}
    if args.from_cache and OUT_PAIRS.exists():
        for line in OUT_PAIRS.read_text(encoding="utf-8").splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            roman, native = parts[0].lower(), nfc(parts[1])
            cnt = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 1
            if is_roman(roman) and is_gujarati(native):
                best[roman] = (native, cnt)
        print(f"loaded cache pairs={len(best)}")
    else:
        if not TAR.exists():
            print(f"ERROR: missing {TAR} (or pass --from-cache with {OUT_PAIRS})")
            return 2
        best = load_pairs_from_tar(TAR)
        with OUT_PAIRS.open("w", encoding="utf-8") as f:
            for roman, (native, cnt) in sorted(best.items(), key=lambda x: -x[1][1]):
                f.write(f"{roman}\t{native}\t{cnt}\n")
        natives = sorted({n for n, _ in best.values()})
        OUT_NATIVE.write_text("\n".join(natives) + "\n", encoding="utf-8")
        print(f"dakshina pairs={len(best)} natives={len(natives)} wrote {OUT_PAIRS}")

    if not BLOB_PATH.exists():
        print(f"ERROR: missing {BLOB_PATH}")
        return 2
    exclude: set[str] = set()
    if TEST_SPLIT.exists():
        exclude = set(json.loads(TEST_SPLIT.read_text(encoding="utf-8")))
        print(f"excluding {len(exclude)} test-split romans from Dakshina soft-fill")
    stats = merge_soft(best, args.max_add, soft_cap=args.soft_cap, exclude_romans=exclude)
    print(f"dakshina soft-fill: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
