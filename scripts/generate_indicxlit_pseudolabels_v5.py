#!/usr/bin/env python3
"""Full-corpus, batched pseudo-label generator for v5 (fork of
generate_indicxlit_pseudolabels_gpu.py).

v4 only distilled the teacher's predictions for the 15+ char long tail
(38,363 romans). The teacher (IndicXlit) actually beats the v4 student by
~7pp top1/recall@6 across the *whole* distribution, not just long words
(see eval/indicxlit_ab_summary.json) -- so v5 lowers --min-length to cover
the full corpus. Doing that at v4's one-roman-at-a-time throughput would
risk spending the whole 6h GPU budget on labeling alone, so this batches
teacher inference via IndicXlitFairseq.nbest_batch() instead. Measured on
an RTX 4080: batch_size=256 gets ~900 words/s (vs. v4's effectively ~29/s
one-at-a-time), so the full ~1.01M-word corpus (min_length=1) labels in
well under 30 minutes -- --max-seconds is still provided as a safety net,
not because it's expected to bind.

Run under .venv-train-gpu:
    .venv-train-gpu/bin/python3 scripts/generate_indicxlit_pseudolabels_v5.py \
        --min-length 1 --batch-size 256 --max-seconds 9000 --resume
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
OUT_JSONL = ROOT / "data" / "external" / "indicxlit_pseudolabels_v5.jsonl"
OUT_META = ROOT / "data" / "external" / "indicxlit_pseudolabels_v5.meta.json"


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
    # Length-bucketed order (not alphabetical): batches of similar-length
    # romans minimize padding waste in nbest_batch().
    return sorted(
        ((roman, native, source) for roman, (native, source) in seen.items()),
        key=lambda row: (len(row[0]), row[0]),
    )


def verify_batching_matches_single(model: IndicXlitFairseq, sample_romans: list[str]) -> None:
    """Guard against a batching bug silently producing different labels
    than the (already-used-in-production) single-item path."""
    if not sample_romans:
        return
    single = [model.nbest(roman, count=4, beam_width=8) for roman in sample_romans]
    batched = model.nbest_batch(sample_romans, count=4, beam_width=8)
    for roman, single_cands, batched_cands in zip(sample_romans, single, batched):
        single_top1 = single_cands[0].native if single_cands else None
        batched_top1 = batched_cands[0].native if batched_cands else None
        if single_top1 != batched_top1:
            raise SystemExit(
                f"FAIL: nbest_batch() disagrees with nbest() for {roman!r}: "
                f"single={single_top1!r} batched={batched_top1!r} -- aborting before "
                "labeling the full corpus with a possibly-broken batched path"
            )
    print(f"verify_batching_matches_single: OK ({len(sample_romans)} spot-checked)", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-length", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--max-seconds", type=float, default=0, help="0 = no cutoff")
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

    print(
        f"labeling {len(targets)} romans (len >= {args.min_length}) on {args.device}, "
        f"batch_size={args.batch_size}, max_seconds={args.max_seconds or 'unlimited'}",
        flush=True,
    )

    model = IndicXlitFairseq(RELEASE_DIR, device=args.device)
    verify_batching_matches_single(model, [t[0] for t in targets[:5]])

    mode = "a" if args.resume and already_done else "w"
    started = time.perf_counter()
    count = 0
    complete = True
    with OUT_JSONL.open(mode, encoding="utf-8") as out:
        for start in range(0, len(targets), args.batch_size):
            elapsed = time.perf_counter() - started
            if args.max_seconds and elapsed >= args.max_seconds:
                complete = False
                print(f"STOP: max_seconds={args.max_seconds} reached at {elapsed:.0f}s", flush=True)
                break

            chunk = targets[start : start + args.batch_size]
            romans = [c[0] for c in chunk]
            try:
                batched_candidates = model.nbest_batch(romans, count=4, beam_width=8)
            except Exception as error:  # noqa: BLE001
                # Fall back to per-item labeling for this one chunk rather than
                # losing the whole batch to a single bad/odd-shaped input.
                print(f"  WARN: batch at {start} failed ({error}); falling back to per-item", flush=True)
                batched_candidates = []
                for roman in romans:
                    try:
                        batched_candidates.append(model.nbest(roman, count=4, beam_width=8))
                    except Exception as item_error:  # noqa: BLE001
                        batched_candidates.append(None)  # type: ignore[arg-type]
                        _ = item_error

            for (roman, gold_native, source), candidates in zip(chunk, batched_candidates):
                if candidates is None:
                    row = {"roman": roman, "candidates": [], "gold_native": gold_native, "source": source, "error": "batch_and_fallback_failed"}
                else:
                    row = {
                        "roman": roman,
                        "candidates": [{"native": c.native, "log_prob": c.log_prob} for c in candidates],
                        "gold_native": gold_native,
                        "source": source,
                    }
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
            out.flush()

            if count % (args.batch_size * 10) < args.batch_size:
                elapsed = time.perf_counter() - started
                rate = count / max(elapsed, 1e-6)
                remaining = (len(targets) - count) / max(rate, 1e-6)
                print(f"  {count}/{len(targets)} ({rate:.1f}/s, ~{remaining:.0f}s remaining)", flush=True)

    elapsed = time.perf_counter() - started
    total_labeled = count + len(already_done)
    OUT_META.write_text(
        json.dumps(
            {
                "source_model": "gu-indicxlit-v1",
                "min_length": args.min_length,
                "romans_labeled": total_labeled,
                "elapsed_seconds": round(elapsed, 1),
                "rate_per_second": round(count / max(elapsed, 1e-6), 2),
                "complete": complete,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{'done' if complete else 'PARTIAL'}: {count} new rows written -> {OUT_JSONL} ({elapsed:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
