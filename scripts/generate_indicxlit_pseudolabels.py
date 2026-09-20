#!/usr/bin/env python3
"""Generate IndicXlit pseudo-labels for long-tail romans (sequence-level
distillation source data for a future CTC retrain).

Targets romans with len >= --min-length from the CTC training corpus
(data/external/{aksharantar,dakshina}_gu_pairs.tsv), the length bucket where
gu-transformer-ctc-v3 is weakest. Filters every candidate through the same
roman-family exclusion logic used by CTC training so the held-out eval sets
never leak into pseudo-labeled data. Runs IndicXlit inference in parallel
across CPU worker processes (no GPU needed for this step).

Run under a venv with onnxruntime installed (.venv-indicxlit or .venv-train-gpu):
    .venv-indicxlit/bin/python3 scripts/generate_indicxlit_pseudolabels.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.train_gujarati_ctc import PAIR_FILES, exclusions, roman_family  # noqa: E402

MODEL_DIR = ROOT / "models" / "artifacts" / "gu-indicxlit-v1"
OUT_JSONL = ROOT / "data" / "external" / "indicxlit_pseudolabels_long.jsonl"
OUT_META = ROOT / "data" / "external" / "indicxlit_pseudolabels_long.meta.json"

_MODEL = None


def _worker_init(model_dir: str) -> None:
    global _MODEL
    sys.path.insert(0, str(ROOT))
    from models.indicxlit_onnx import IndicXlitOnnx

    _MODEL = IndicXlitOnnx(model_dir)


def _label_one(item: tuple[str, str | None, str]) -> dict:
    roman, gold_native, source = item
    try:
        candidates = _MODEL.nbest(roman, count=4, beam_width=8)
    except Exception as error:  # noqa: BLE001 - a handful of ORT quantized-graph
        # failures on specific dynamic shapes shouldn't take down the whole
        # labeling run; skip this roman and keep going (downstream training
        # data loading just ignores rows with no candidates).
        return {"roman": roman, "candidates": [], "gold_native": gold_native, "source": source, "error": str(error)}
    return {
        "roman": roman,
        "candidates": [{"native": c.native, "log_prob": c.log_prob} for c in candidates],
        "gold_native": gold_native,
        "source": source,
    }


def collect_targets(min_length: int) -> list[tuple[str, str | None, str]]:
    excluded_romans, _excluded_natives = exclusions()
    seen: dict[str, tuple[str | None, str]] = {}
    for source_index, path in enumerate(PAIR_FILES):
        if not path.exists():
            continue
        source_name = path.stem.replace("_gu_pairs", "")
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            roman = fields[0].strip().lower()
            native = unicodedata.normalize("NFC", fields[1].strip())
            if len(roman) < min_length:
                continue
            if roman_family(roman) in excluded_romans:
                continue
            if not roman.isascii() or not roman.isalpha():
                # Match the roman validity gate loosely; exact regex reuse
                # happens implicitly since these rows already passed it once
                # when they were written into the pair TSVs.
                continue
            if roman not in seen:
                seen[roman] = (native, source_name)
    return [(roman, native, source) for roman, (native, source) in sorted(seen.items())]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-length", type=int, default=15)
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--limit", type=int, default=0, help="0 = no cap")
    parser.add_argument("--resume", action="store_true", help="skip romans already in the output file")
    args = parser.parse_args()

    targets = collect_targets(args.min_length)
    if args.limit > 0:
        targets = targets[: args.limit]

    already_done: set[str] = set()
    if args.resume and OUT_JSONL.exists():
        for line in OUT_JSONL.read_text(encoding="utf-8").splitlines():
            if line:
                already_done.add(json.loads(line)["roman"])
        targets = [t for t in targets if t[0] not in already_done]
        print(f"resuming: {len(already_done)} already labeled, {len(targets)} remaining")

    print(f"labeling {len(targets)} romans (len >= {args.min_length}) with {args.workers} workers")

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    mode = "a" if args.resume and already_done else "w"
    with Pool(processes=args.workers, initializer=_worker_init, initargs=(str(MODEL_DIR),)) as pool, \
            OUT_JSONL.open(mode, encoding="utf-8") as out:
        for row in pool.imap_unordered(_label_one, targets, chunksize=64):
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
            if count % 2000 == 0:
                print(f"  {count}/{len(targets)}")

    model_hash = hashlib.sha256((MODEL_DIR / "indicxlit_encoder.onnx").read_bytes()).hexdigest()
    OUT_META.write_text(
        json.dumps(
            {
                "source_model": "gu-indicxlit-v1",
                "encoder_sha256": model_hash,
                "min_length": args.min_length,
                "romans_labeled": count,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {count} rows -> {OUT_JSONL}")
    print(f"wrote {OUT_META}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
