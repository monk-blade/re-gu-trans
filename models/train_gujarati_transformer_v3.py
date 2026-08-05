#!/usr/bin/env python3
"""Train a CUDA-aware teacher or distilled Gujarati Transformer-CTC v3 model."""
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
except ModuleNotFoundError:
    from gujarati_ctc import valid_gujarati_word
    from train_gujarati_ctc import load_pairs, roman_family

ROOT = Path(__file__).resolve().parents[1]
MODEL_VERSION = "gu-transformer-ctc-v3"


def file_digest(path: Path) -> str | None:
    if not path.exists():
        return None
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def source_provenance() -> list[dict]:
    external = ROOT / "data" / "external"
    sources = (
        (
            "aksharantar-gujarati",
            "https://huggingface.co/datasets/ai4bharat/Aksharantar",
            "CC-BY-4.0 and CC0",
            "aksharantar_guj.zip",
            "aksharantar_gu_pairs.tsv",
        ),
        (
            "dakshina-gujarati",
            "https://github.com/google-research-datasets/dakshina",
            "CC-BY-SA-4.0",
            "dakshina_dataset_v1.0.tar",
            "dakshina_gu_pairs.tsv",
        ),
    )
    return [
        {
            "label": label,
            "url": url,
            "license": license_name,
            "cache": cache,
            "cache_sha256": file_digest(external / cache),
            "pairs": pairs,
            "pairs_sha256": file_digest(external / pairs),
        }
        for label, url, license_name, cache, pairs in sources
    ]


def split_pairs(pairs: list[tuple[str, str]], validation_percent: int = 2):
    train: list[tuple[str, str]] = []
    validation: list[tuple[str, str]] = []
    for pair in pairs:
        family = roman_family(pair[0])
        bucket = int(hashlib.sha256(family.encode()).hexdigest()[:8], 16) % 100
        (validation if bucket < validation_percent else train).append(pair)
    return train, validation


def noisy_roman(value: str, rng: random.Random) -> str:
    variants = [value]
    if "w" in value:
        variants.append(value.replace("w", "v"))
    if "v" in value:
        variants.append(value.replace("v", "w"))
    for source, target in (("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("sh", "s")):
        if source in value:
            variants.append(value.replace(source, target, 1))
    if "h" in value and len(value) > 3:
        at = value.index("h")
        variants.append(value[:at] + value[at + 1 :])
    return rng.choice(variants)


class PairDataset(Dataset):
    def __init__(self, pairs, input_index, output_index, augment: bool, seed: int):
        # Short romans are disproportionately important in interactive use and
        # are easy for a CTC model to underfit. Keep the original rows and add
        # two deterministic copies of the short-input slice, matching the v2
        # training contract without changing validation membership.
        base = list(pairs)
        short = [pair for pair in base if len(pair[0]) <= 4]
        self.pairs = base + short + short
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


def collate(rows):
    inputs, targets = zip(*rows)
    input_lengths = torch.tensor([len(row) * 2 for row in inputs], dtype=torch.long)
    padded = nn.utils.rnn.pad_sequence(inputs, batch_first=True)
    target_lengths = torch.tensor([len(row) for row in targets], dtype=torch.long)
    return padded, input_lengths, torch.cat(targets), target_lengths


class SelfAttention(nn.Module):
    def __init__(self, dimension: int, heads: int):
        super().__init__()
        if dimension % heads:
            raise ValueError("dimension must be divisible by heads")
        self.heads = heads
        self.head_dimension = dimension // heads
        self.scale = self.head_dimension**-0.5
        self.query = nn.Linear(dimension, dimension)
        self.key = nn.Linear(dimension, dimension)
        self.value = nn.Linear(dimension, dimension)
        self.output = nn.Linear(dimension, dimension)

    def forward(self, values, padding_mask):
        batch, length = values.shape[:2]
        shape = (batch, length, self.heads, self.head_dimension)
        query = self.query(values).reshape(shape).transpose(1, 2)
        key = self.key(values).reshape(shape).transpose(1, 2)
        value = self.value(values).reshape(shape).transpose(1, 2)
        scores = torch.matmul(query, key.transpose(-2, -1)) * self.scale
        scores = scores.masked_fill(padding_mask[:, None, None, :], -10_000.0)
        attended = torch.matmul(torch.softmax(scores, dim=-1), value)
        attended = attended.transpose(1, 2).reshape(batch, length, -1)
        return self.output(attended)


class TransformerBlock(nn.Module):
    def __init__(self, dimension: int, heads: int, feedforward: int, dropout: float):
        super().__init__()
        self.attention_norm = nn.LayerNorm(dimension)
        self.attention = SelfAttention(dimension, heads)
        self.feedforward_norm = nn.LayerNorm(dimension)
        self.feedforward = nn.Sequential(
            nn.Linear(dimension, feedforward),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(feedforward, dimension),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, values, padding_mask):
        values = values + self.dropout(self.attention(self.attention_norm(values), padding_mask))
        return values + self.dropout(self.feedforward(self.feedforward_norm(values)))


class GujaratiTransformerCtcV3(nn.Module):
    def __init__(self, input_size: int, output_size: int, config: dict[str, int | float]):
        super().__init__()
        self.config = dict(config)
        dimension = int(config["dimension"])
        self.embedding = nn.Embedding(input_size, dimension, padding_idx=0)
        self.position = nn.Embedding(int(config["max_frames"]), dimension)
        self.encoder = nn.ModuleList(
            TransformerBlock(
                dimension,
                int(config["heads"]),
                int(config["feedforward"]),
                float(config["dropout"]),
            )
            for _ in range(int(config["layers"]))
        )
        self.final_norm = nn.LayerNorm(dimension)
        self.output = nn.Linear(dimension, output_size)

    def forward(self, roman_ids):
        repeated = torch.repeat_interleave(roman_ids, 2, dim=1)
        if repeated.shape[1] > self.position.num_embeddings:
            raise ValueError("roman input exceeds configured max_frames")
        positions = torch.arange(repeated.shape[1], device=roman_ids.device).unsqueeze(0)
        encoded = self.embedding(repeated) + self.position(positions)
        padding_mask = repeated.eq(0)
        for block in self.encoder:
            encoded = block(encoded, padding_mask)
        return self.output(self.final_norm(encoded))


def model_config(args) -> dict[str, int | float]:
    return {
        "dimension": args.dimension,
        "layers": args.layers,
        "heads": args.heads,
        "feedforward": args.feedforward,
        "max_frames": args.max_frames,
        "dropout": args.dropout,
    }


def resolve_device(requested: str) -> torch.device:
    if requested == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA requested but torch.cuda.is_available() is false")
    if requested == "auto":
        requested = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(requested)
    if device.type == "cuda":
        print(json.dumps({
            "cuda": True,
            "device": torch.cuda.get_device_name(device),
            "torch_cuda": torch.version.cuda,
            "memory_total_mb": round(torch.cuda.get_device_properties(device).total_memory / 2**20),
        }), flush=True)
    return device


def amp_context(device: torch.device, mode: str):
    if device.type != "cuda" or mode == "off":
        return nullcontext(), None
    if mode == "bf16" or (mode == "auto" and torch.cuda.is_bf16_supported()):
        return torch.autocast("cuda", dtype=torch.bfloat16), torch.bfloat16
    return torch.autocast("cuda", dtype=torch.float16), torch.float16


def make_scaler(device: torch.device, dtype):
    enabled = device.type == "cuda" and dtype == torch.float16
    return torch.amp.GradScaler("cuda", enabled=enabled)


def ctc_loss(logits, targets, input_lengths, target_lengths):
    return F.ctc_loss(
        logits.float().log_softmax(-1).transpose(0, 1),
        targets,
        input_lengths,
        target_lengths,
        blank=0,
        zero_infinity=True,
    )


def distillation_loss(student, teacher, input_lengths, temperature: float):
    steps = student.shape[1]
    positions = torch.arange(steps, device=student.device)[None, :]
    mask = positions < input_lengths[:, None]
    student_log = F.log_softmax(student.float() / temperature, dim=-1)
    teacher_prob = F.softmax(teacher.float() / temperature, dim=-1)
    per_frame = F.kl_div(student_log, teacher_prob, reduction="none").sum(-1)
    return (per_frame * mask).sum() / mask.sum().clamp_min(1) * temperature**2


def batch_from_dataset(dataset, indexes):
    return collate([dataset[index] for index in indexes])


def autotune_batch_size(model, dataset, device, args, teacher=None):
    candidates = [1024, 768, 512, 384, 256, 192, 128, 96, 64, 32]
    candidates = [value for value in candidates if value <= len(dataset)]
    if args.batch_size > 0:
        candidates = [args.batch_size]
    for size in candidates:
        try:
            model.train()
            inputs, lengths, targets, target_lengths = batch_from_dataset(dataset, range(size))
            inputs, lengths = inputs.to(device), lengths.to(device)
            targets, target_lengths = targets.to(device), target_lengths.to(device)
            with torch.enable_grad():
                student_logits = model(inputs)
                loss = ctc_loss(student_logits, targets, lengths, target_lengths)
                if teacher is not None:
                    with torch.no_grad():
                        teacher_logits = teacher(inputs)
                    loss = loss + args.distill_weight * distillation_loss(
                        student_logits, teacher_logits, lengths, args.temperature
                    )
                loss.backward()
            model.zero_grad(set_to_none=True)
            if teacher is not None:
                teacher.zero_grad(set_to_none=True)
            if device.type == "cuda":
                torch.cuda.empty_cache()
            print(json.dumps({"auto_batch_size": size}), flush=True)
            return size
        except (RuntimeError, torch.cuda.OutOfMemoryError) as error:
            if device.type != "cuda" or "out of memory" not in str(error).lower():
                raise
            model.zero_grad(set_to_none=True)
            if teacher is not None:
                teacher.zero_grad(set_to_none=True)
            torch.cuda.empty_cache()
    raise SystemExit("unable to find a CUDA batch size")


def validation_loss(model, loader, device, amp_mode):
    model.eval()
    total = 0.0
    with torch.no_grad():
        for inputs, lengths, targets, target_lengths in loader:
            inputs, lengths = inputs.to(device, non_blocking=True), lengths.to(device, non_blocking=True)
            targets, target_lengths = targets.to(device, non_blocking=True), target_lengths.to(device, non_blocking=True)
            with amp_context(device, amp_mode)[0]:
                logits = model(inputs)
            total += float(ctc_loss(logits, targets, lengths, target_lengths))
    return total / max(1, len(loader))


def load_checkpoint(path: Path, device: torch.device):
    checkpoint = torch.load(path, map_location=device, weights_only=False)
    config = checkpoint["model_config"]
    model = GujaratiTransformerCtcV3(
        len(checkpoint["input_vocab"]), len(checkpoint["output_vocab"]), config
    ).to(device)
    model.load_state_dict(checkpoint["model"])
    return model, checkpoint


def save_checkpoint(path, model, optimizer, scheduler, scaler, epoch, best_loss, metadata):
    state = model.state_dict()
    torch.save(
        {
            "model": state,
            "model_config": metadata["model_config"],
            "input_vocab": metadata["input_vocab"],
            "output_vocab": metadata["output_vocab"],
            "optimizer": optimizer.state_dict(),
            "scheduler": scheduler.state_dict(),
            "scaler": scaler.state_dict(),
            "epoch": epoch,
            "best_loss": best_loss,
            "metadata": metadata,
        },
        path,
    )


def export_model(model, artifact: Path, metadata):
    artifact.mkdir(parents=True, exist_ok=True)
    model = model.cpu().eval()
    (artifact / "vocab.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (artifact / "vocab.tsv").write_text(
        "input\t" + "\t".join(metadata["input_vocab"]) + "\n"
        + "output\t" + "\t".join(metadata["output_vocab"]) + "\n"
        + "version\t" + metadata["model_version"] + "\n",
        encoding="utf-8",
    )
    sample = torch.ones((1, 12), dtype=torch.long)
    torch.onnx.export(
        model,
        sample,
        artifact / "gujarati_xlit.onnx",
        input_names=["roman_ids"],
        output_names=["logits"],
        dynamic_axes={
            "roman_ids": {0: "batch", 1: "roman_length"},
            "logits": {0: "batch", 1: "frames"},
        },
        opset_version=17,
        dynamo=False,
    )
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(
        str(artifact / "gujarati_xlit.onnx"),
        str(artifact / "gujarati_xlit.int8.onnx"),
        weight_type=QuantType.QInt8,
    )
    print(json.dumps({"exported": str(artifact), "model_version": MODEL_VERSION}), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("teacher", "student"), default="teacher")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--teacher-checkpoint", type=Path)
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
    parser.add_argument("--dimension", type=int, default=384)
    parser.add_argument("--layers", type=int, default=8)
    parser.add_argument("--heads", type=int, default=8)
    parser.add_argument("--feedforward", type=int, default=1536)
    parser.add_argument("--max-frames", type=int, default=96)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--temperature", type=float, default=2.0)
    parser.add_argument("--distill-weight", type=float, default=0.35)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--export", action="store_true")
    args = parser.parse_args()
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = resolve_device(args.device)
    args.output.mkdir(parents=True, exist_ok=True)

    pairs = [pair for pair in load_pairs(args.train_limit, args.seed) if valid_gujarati_word(pair[1])]
    if not pairs:
        raise SystemExit("no valid training pairs; ingest public pair sources first")
    train_pairs, validation_pairs = split_pairs(pairs)
    input_vocab = ["<pad>", "<unk>", *sorted(set("".join(roman for roman, _ in pairs)))]
    output_vocab = ["<blank>", *sorted(set("".join(native for _, native in pairs)))]
    input_index = {char: index for index, char in enumerate(input_vocab)}
    output_index = {char: index for index, char in enumerate(output_vocab)}
    train_data = PairDataset(train_pairs, input_index, output_index, True, args.seed)
    validation_data = PairDataset(validation_pairs, input_index, output_index, False, args.seed)
    config = model_config(args)
    teacher = None
    if args.mode == "student":
        if not args.teacher_checkpoint:
            raise SystemExit("--teacher-checkpoint is required for student mode")
        teacher, teacher_checkpoint = load_checkpoint(args.teacher_checkpoint, device)
        teacher.eval()
        if teacher_checkpoint["input_vocab"] != input_vocab or teacher_checkpoint["output_vocab"] != output_vocab:
            raise SystemExit("teacher and student vocabularies differ")
    model = GujaratiTransformerCtcV3(len(input_vocab), len(output_vocab), config).to(device)
    metadata = {
        "version": 3,
        "model_version": MODEL_VERSION,
        "architecture": "configurable-transformer-encoder-ctc-distilled" if args.mode == "student" else "large-transformer-encoder-ctc-teacher",
        "model_config": config,
        "training_pairs": len(train_pairs),
        "validation_pairs": len(validation_pairs),
        "training_epochs": args.epochs,
        "benchmark_family_exclusion": True,
        "family_disjoint_validation": True,
        "short_input_oversampling": True,
        "roman_noise_augmentation": True,
        "distilled": args.mode == "student",
        "teacher_checkpoint": str(args.teacher_checkpoint) if args.teacher_checkpoint else None,
        "input_vocab": input_vocab,
        "input_unk": input_index["<unk>"],
        "output_vocab": output_vocab,
        "training_digest": hashlib.sha256("\n".join(f"{r}\t{n}" for r, n in train_pairs).encode()).hexdigest(),
        "source_provenance": source_provenance(),
    }
    batch_size = autotune_batch_size(model, train_data, device, args, teacher)
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
                student_logits = model(inputs)
                loss = ctc_loss(student_logits, targets, lengths, target_lengths)
                if teacher is not None:
                    with torch.no_grad():
                        teacher_logits = teacher(inputs)
                    loss = loss + args.distill_weight * distillation_loss(
                        student_logits, teacher_logits, lengths, args.temperature
                    )
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
        export_model(model, args.output, metadata)
    print(json.dumps({"output": str(args.output), "mode": args.mode, "model_version": MODEL_VERSION}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
