#!/usr/bin/env python3
"""Train Gujarati Transformer-CTC v4: same architecture as v3's student, but
trained on the gold corpus augmented/overridden with IndicXlit sequence-level
pseudo-labels for long romans (see scripts/generate_indicxlit_pseudolabels.py).

Unlike v3, there is no frame-level teacher-student distillation here (IndicXlit
is architecturally incompatible with that scheme -- autoregressive, variable
output length, different vocab). This trains with plain CTC loss only; the
"distillation" happens entirely in the training *data* (IndicXlit's own
predictions become training labels for long words), not in the loss function.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import time
from contextlib import nullcontext
from pathlib import Path

import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, Dataset

try:
    from models.gujarati_ctc import valid_gujarati_word
    from models.train_gujarati_ctc import load_pairs, roman_family
    from models.train_gujarati_transformer_v3 import (
        GujaratiTransformerCtcV3,
        PairDataset,
        amp_context,
        collate,
        export_model as export_model_v3,
        make_scaler,
        model_config,
        noisy_roman,
        resolve_device,
        save_checkpoint,
        source_provenance,
        split_pairs,
        validation_loss,
    )
except ModuleNotFoundError:
    from gujarati_ctc import valid_gujarati_word
    from train_gujarati_ctc import load_pairs, roman_family
    from train_gujarati_transformer_v3 import (
        GujaratiTransformerCtcV3,
        PairDataset,
        amp_context,
        collate,
        export_model as export_model_v3,
        make_scaler,
        model_config,
        noisy_roman,
        resolve_device,
        save_checkpoint,
        source_provenance,
        split_pairs,
        validation_loss,
    )

ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = "gu-transformer-ctc-v4"


def ctc_loss(logits, targets, input_lengths, target_lengths):
    return F.ctc_loss(
        logits.float().log_softmax(-1).transpose(0, 1),
        targets,
        input_lengths,
        target_lengths,
        blank=0,
        zero_infinity=True,
    )


def load_pseudolabels(
    path: Path,
    gold_by_roman: dict[str, str],
    confidence_margin: float,
    min_length: int,
) -> tuple[list[tuple[str, str]], set[str], dict]:
    """Sequence-level distillation data: IndicXlit's own predictions as labels.

    - Romans with no existing gold label: accept IndicXlit's top-1 outright
      (no conflicting label to weigh against).
    - Romans with an existing gold label: only override when IndicXlit's
      top-1 disagrees with gold AND its log-prob margin over its own 2nd-best
      candidate clears `confidence_margin` (both must hold). Otherwise keep
      gold untouched -- avoids injecting IndicXlit's own errors as noise into
      an area where a presumably-verified label already exists.

    Returns (added_or_overridden_pairs, all_long_romans, stats). The oversample
    set (`all_long_romans`) is every roman IndicXlit labeled at this length,
    regardless of whether its label was overridden -- at full training scale
    almost every long roman here already has a matching gold label (they were
    sourced from the same corpus), so restricting oversampling to only the
    label-changed slice would barely touch anything; the actual fix for CTC's
    long-word underfitting is *more training signal density* on long words
    generally (mirroring the existing short-word oversample tier), not just
    correcting the small number of disagreements.
    """
    added: list[tuple[str, str]] = []
    all_long_romans: set[str] = set()
    stats = {"total": 0, "novel_added": 0, "overridden": 0, "kept_gold": 0, "rejected_invalid": 0}
    if not path.exists():
        return added, all_long_romans, stats
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        roman = str(row.get("roman") or "")
        if len(roman) < min_length:
            continue
        candidates = row.get("candidates") or []
        if not candidates:
            continue
        stats["total"] += 1
        top1 = candidates[0]["native"]
        top1_logprob = float(candidates[0]["log_prob"])
        margin = (
            top1_logprob - float(candidates[1]["log_prob"])
            if len(candidates) > 1
            else float("inf")
        )
        if not valid_gujarati_word(top1):
            stats["rejected_invalid"] += 1
            continue
        gold = gold_by_roman.get(roman)
        if gold is None:
            added.append((roman, top1))
            all_long_romans.add(roman)
            stats["novel_added"] += 1
        elif top1 != gold and margin >= confidence_margin:
            added.append((roman, top1))
            all_long_romans.add(roman)
            stats["overridden"] += 1
        else:
            all_long_romans.add(roman)
            stats["kept_gold"] += 1
    return added, all_long_romans, stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-limit", type=int, default=0)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=0, help="0 enables CUDA batch-size probing")
    parser.add_argument("--seed", type=int, default=29)
    parser.add_argument("--learning-rate", type=float, default=6e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument("--amp", choices=("auto", "off", "fp16", "bf16"), default="auto")
    parser.add_argument("--num-workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--gradient-accumulation", type=int, default=1)
    parser.add_argument("--dimension", type=int, default=256)
    parser.add_argument("--layers", type=int, default=6)
    parser.add_argument("--heads", type=int, default=8)
    parser.add_argument("--feedforward", type=int, default=768)
    parser.add_argument("--max-frames", type=int, default=96)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--export", action="store_true")
    parser.add_argument(
        "--pseudolabel-file",
        type=Path,
        default=ROOT / "data" / "external" / "indicxlit_pseudolabels_long.jsonl",
    )
    parser.add_argument("--pseudolabel-confidence-margin", type=float, default=1.0)
    parser.add_argument("--long-roman-threshold", type=int, default=15)
    parser.add_argument("--long-pair-oversample", type=int, default=2)
    args = parser.parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = resolve_device(args.device)
    args.output.mkdir(parents=True, exist_ok=True)

    gold_pairs = [pair for pair in load_pairs(args.train_limit, args.seed) if valid_gujarati_word(pair[1])]
    if not gold_pairs:
        raise SystemExit("no valid training pairs; ingest public pair sources first")
    gold_by_roman = {roman: native for roman, native in gold_pairs}

    pseudo_pairs, long_romans, pseudo_stats = load_pseudolabels(
        args.pseudolabel_file, gold_by_roman, args.pseudolabel_confidence_margin, args.long_roman_threshold
    )
    print(json.dumps({"pseudolabel_stats": pseudo_stats}), flush=True)

    # Merge: pseudo pairs replace/add on top of gold (dict keyed by roman so
    # an override actually replaces the gold row rather than duplicating it).
    merged = dict(gold_pairs)
    for roman, native in pseudo_pairs:
        merged[roman] = native
    pairs = list(merged.items())

    train_pairs, validation_pairs = split_pairs(pairs)
    input_vocab = ["<pad>", "<unk>", *sorted(set("".join(roman for roman, _ in pairs)))]
    output_vocab = ["<blank>", *sorted(set("".join(native for _, native in pairs)))]
    input_index = {char: index for index, char in enumerate(input_vocab)}
    output_index = {char: index for index, char in enumerate(output_vocab)}

    train_data = LongOversampledPairDataset(
        train_pairs, input_index, output_index, True, args.seed, long_romans, args.long_pair_oversample
    )
    validation_data = PairDataset(validation_pairs, input_index, output_index, False, args.seed)

    config = model_config(args)
    model = GujaratiTransformerCtcV3(len(input_vocab), len(output_vocab), config).to(device)
    metadata = {
        "version": 4,
        "model_version": MODEL_VERSION,
        "architecture": "configurable-transformer-encoder-ctc-sequence-distilled",
        "model_config": config,
        "training_pairs": len(train_pairs),
        "validation_pairs": len(validation_pairs),
        "training_epochs": args.epochs,
        "benchmark_family_exclusion": True,
        "family_disjoint_validation": True,
        "short_input_oversampling": True,
        "long_pair_oversampling": True,
        "roman_noise_augmentation": True,
        "distilled": True,
        "distillation_method": "sequence-level-pseudolabel",
        "pseudolabel_source_model": "gu-indicxlit-v1",
        "pseudolabel_stats": pseudo_stats,
        "pseudolabel_confidence_margin": args.pseudolabel_confidence_margin,
        "long_roman_threshold": args.long_roman_threshold,
        "long_pair_oversample": args.long_pair_oversample,
        "input_vocab": input_vocab,
        "input_unk": input_index["<unk>"],
        "output_vocab": output_vocab,
        "training_digest": hashlib.sha256("\n".join(f"{r}\t{n}" for r, n in train_pairs).encode()).hexdigest(),
        "source_provenance": source_provenance(),
    }
    batch_size = autotune_batch_size(model, train_data, device, args)
    loader_kwargs = {
        "batch_size": batch_size,
        "collate_fn": collate,
        "num_workers": args.num_workers,
        "pin_memory": device.type == "cuda",
    }
    if args.num_workers:
        loader_kwargs["persistent_workers"] = True
    train_loader = DataLoader(train_data, shuffle=True, **loader_kwargs)
    validation_loader = DataLoader(validation_data, shuffle=False, **loader_kwargs)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, args.epochs))
    _amp, amp_dtype = amp_context(device, args.amp)
    scaler = make_scaler(device, amp_dtype)
    start_epoch = 0
    best_loss = math.inf
    if args.resume:
        resume = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(resume["model"])
        optimizer.load_state_dict(resume["optimizer"])
        scheduler.load_state_dict(resume["scheduler"])
        scaler.load_state_dict(resume.get("scaler", {}))
        start_epoch = int(resume["epoch"]) + 1
        best_loss = float(resume.get("best_loss", math.inf))
    for epoch in range(start_epoch, args.epochs):
        model.train()
        started = time.perf_counter()
        total = 0.0
        optimizer.zero_grad(set_to_none=True)
        for step, (inputs, lengths, targets, target_lengths) in enumerate(train_loader, 1):
            inputs, lengths = inputs.to(device, non_blocking=True), lengths.to(device, non_blocking=True)
            targets, target_lengths = targets.to(device, non_blocking=True), target_lengths.to(device, non_blocking=True)
            with amp_context(device, args.amp)[0]:
                logits = model(inputs)
                loss = ctc_loss(logits, targets, lengths, target_lengths)
            scaled_loss = loss / max(1, args.gradient_accumulation)
            scaler.scale(scaled_loss).backward()
            if step % max(1, args.gradient_accumulation) == 0 or step == len(train_loader):
                scaler.unscale_(optimizer)
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
            total += float(loss.detach())
            if step % 250 == 0:
                print(json.dumps({"epoch": epoch + 1, "step": step, "loss": round(total / step, 4)}), flush=True)
        dev_loss = validation_loss(model, validation_loader, device, args.amp)
        scheduler.step()
        elapsed = time.perf_counter() - started
        print(json.dumps({
            "epoch": epoch + 1,
            "loss": round(total / max(1, len(train_loader)), 4),
            "validation_loss": round(dev_loss, 4),
            "epoch_seconds": round(elapsed, 2),
            "samples_per_second": round(len(train_data) / max(elapsed, 1e-6), 1),
        }), flush=True)
        save_checkpoint(args.output / "checkpoint_last.pt", model, optimizer, scheduler, scaler, epoch, best_loss, metadata)
        if dev_loss < best_loss:
            best_loss = dev_loss
            save_checkpoint(args.output / "checkpoint_best.pt", model, optimizer, scheduler, scaler, epoch, best_loss, metadata)
    model.load_state_dict(torch.load(args.output / "checkpoint_best.pt", map_location=device, weights_only=False)["model"])
    metadata["best_validation_loss"] = best_loss
    metadata["batch_size"] = batch_size
    metadata["device"] = str(device)
    metadata["torch_version"] = torch.__version__
    metadata["torch_cuda"] = torch.version.cuda
    (args.output / "vocab.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.export:
        export_model_v3(model, args.output, metadata)
    print(json.dumps({"output": str(args.output), "model_version": MODEL_VERSION}), flush=True)
    return 0


class LongOversampledPairDataset(Dataset):
    """Like PairDataset's short-word oversampling, but for the long/pseudo-
    labeled slice, keyed by an explicit set of romans rather than a length
    check alone (so only pairs that actually came from/were confirmed by
    pseudo-labeling get the extra weight, not every long gold word)."""

    def __init__(self, pairs, input_index, output_index, augment, seed, long_romans: set[str], oversample: int):
        base = list(pairs)
        short = [pair for pair in base if len(pair[0]) <= 4]
        long_pairs = [pair for pair in base if pair[0] in long_romans]
        self.pairs = base + short + short + long_pairs * max(0, oversample - 1)
        self.input_index = input_index
        self.output_index = output_index
        self.augment = augment
        self.seed = seed

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, index):
        roman, native = self.pairs[index]
        if self.augment:
            roman = noisy_roman(roman, random.Random(self.seed + index * 104729))
        return (
            torch.tensor([self.input_index.get(char, 1) for char in roman], dtype=torch.long),
            torch.tensor([self.output_index[char] for char in native], dtype=torch.long),
        )


def autotune_batch_size(model, dataset, device, args):
    candidates = [1024, 768, 512, 384, 256, 192, 128, 96, 64, 32]
    candidates = [value for value in candidates if value <= len(dataset)]
    if args.batch_size > 0:
        candidates = [args.batch_size]
    for size in candidates:
        try:
            model.train()
            inputs, lengths, targets, target_lengths = collate([dataset[i] for i in range(size)])
            inputs, lengths = inputs.to(device), lengths.to(device)
            targets, target_lengths = targets.to(device), target_lengths.to(device)
            with torch.enable_grad():
                logits = model(inputs)
                loss = ctc_loss(logits, targets, lengths, target_lengths)
                loss.backward()
            model.zero_grad(set_to_none=True)
            if device.type == "cuda":
                torch.cuda.empty_cache()
            print(json.dumps({"auto_batch_size": size}), flush=True)
            return size
        except (RuntimeError, torch.cuda.OutOfMemoryError) as error:
            if device.type != "cuda" or "out of memory" not in str(error).lower():
                raise
            model.zero_grad(set_to_none=True)
            torch.cuda.empty_cache()
    raise SystemExit("unable to find a CUDA batch size")


if __name__ == "__main__":
    raise SystemExit(main())
