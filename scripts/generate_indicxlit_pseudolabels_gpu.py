#!/usr/bin/env python3
"""GPU, single-process variant of generate_indicxlit_pseudolabels.py.

The CPU multiprocess version (24 parallel ONNX Runtime workers) overloaded
the machine thermally. This uses the direct fairseq checkpoint on CUDA in a
single process instead -- much lower system load (one process, mostly GPU
work), safe to run unattended.

Run under .venv-train-gpu (has CUDA torch + fairseq + the py3.11 compat patch
already applied):
    .venv-train-gpu/bin/python3 scripts/generate_indicxlit_pseudolabels_gpu.py --resume
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import eval._fairseq_py311_compat  # noqa: E402,F401  (must precede fairseq import)

from models.train_gujarati_ctc import PAIR_FILES, exclusions, roman_family  # noqa: E402
from models.indicxlit_fairseq import IndicXlitFairseq  # noqa: E402

RELEASE_DIR = ROOT / "data" / "external" / "indicxlit" / "release"
OUT_JSONL = ROOT / "data" / "external" / "indicxlit_pseudolabels_long.jsonl"
OUT_META = ROOT / "data" / "external" / "indicxlit_pseudolabels_long.meta.json"


def collect_targets(min_length: int):
    excluded_romans, _ = exclusions()
    seen: dict[str, tuple[str | None, str]] = {}
    for path in PAIR_FILES:
        if not path.exists():
            continue
        source_name = path.stem.replace("_gu_pairs", "")
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            roman = fields[0].strip().lower()
            native = fields[1].strip()
            if len(roman) < min_length:
                continue
            if roman_family(roman) in excluded_romans:
                continue
            if not roman.isascii() or not roman.isalpha():
                continue
            if roman not in seen:
                seen[roman] = (native, source_name)
    return [(roman, native, source) for roman, (native, source) in sorted(seen.items())]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-length", type=int, default=15)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    targets = collect_targets(args.min_length)
    if args.limit > 0:
        targets = targets[: args.limit]

    already_done: set[str] = set()
    if args.resume and OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if line:
                row = json.loads(line)
                if row.get("candidates"):  # keep retrying rows that errored out
                    already_done.add(row["roman"])
        targets = [t for t in targets if t[0] not in already_done]
        print(f"resuming: {len(already_done)} already labeled, {len(targets)} remaining", flush=True)

    print(f"labeling {len(targets)} romans (len >= {args.min_length}) on {args.device}", flush=True)

    model = IndicXlitFairseq(RELEASE_DIR, device=args.device)

    mode = "a" if args.resume and already_done else "w"
    started = time.perf_counter()
    count = 0
    with OUT_JSONL.open(mode, encoding="utf-8") as out:
        for roman, gold_native, source in targets:
            try:
                candidates = model.nbest(roman, count=4, beam_width=8)
                row = {
                    "roman": roman,
                    "candidates": [{"native": c.native, "log_prob": c.log_prob} for c in candidates],
                    "gold_native": gold_native,
                    "source": source,
                }
            except Exception as error:  # noqa: BLE001
                row = {"roman": roman, "candidates": [], "gold_native": gold_native, "source": source, "error": str(error)}
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            count += 1
            if count % 1000 == 0:
                elapsed = time.perf_counter() - started
                rate = count / elapsed
                remaining = (len(targets) - count) / max(rate, 1e-6)
                print(f"  {count}/{len(targets)} ({rate:.1f}/s, ~{remaining:.0f}s remaining)", flush=True)

    OUT_META.write_text(
        json.dumps({"source_model": "gu-indicxlit-v1", "min_length": args.min_length, "romans_labeled": count + len(already_done)}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"done: {count} new rows written -> {OUT_JSONL}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
