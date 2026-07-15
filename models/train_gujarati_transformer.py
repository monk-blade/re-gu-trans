#!/usr/bin/env python3
"""Train and export the compact Gujarati Transformer-CTC v2 model."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

try:
    from models.train_gujarati_ctc import load_pairs, roman_family
    from models.gujarati_ctc import valid_gujarati_word
except ModuleNotFoundError:
    from train_gujarati_ctc import load_pairs, roman_family
    from gujarati_ctc import valid_gujarati_word

ROOT = Path(__file__).resolve().parents[1]


def split_pairs(
    pairs: list[tuple[str, str]], validation_percent: int = 2
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    train: list[tuple[str, str]] = []
    validation: list[tuple[str, str]] = []
    for pair in pairs:
        family = roman_family(pair[0])
        bucket = int(hashlib.sha256(family.encode()).hexdigest()[:8], 16) % 100
        (validation if bucket < validation_percent else train).append(pair)
    return train, validation


def noisy_roman(value: str, rng: random.Random) -> str:
    variants = [value]
    variants.append(value.replace("w", "v") if "w" in value else value.replace("v", "w"))
    for source, target in (("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("sh", "s")):
        if source in value:
            variants.append(value.replace(source, target, 1))
    if "h" in value and len(value) > 3:
        at = value.index("h")
        variants.append(value[:at] + value[at + 1 :])
    return rng.choice(variants)


class TransformerPairDataset(Dataset):
    def __init__(self, pairs, input_index, output_index, augment: bool, seed: int):
        expanded = list(pairs)
        # Short words are underrepresented but dominate interactive ambiguity.
        expanded.extend(pair for pair in pairs if len(pair[0]) <= 4 for _ in range(2))
        self.pairs = expanded
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
    lengths = torch.tensor([len(row) * 2 for row in inputs], dtype=torch.long)
    padded = nn.utils.rnn.pad_sequence(inputs, batch_first=True)
    target_lengths = torch.tensor([len(row) for row in targets], dtype=torch.long)
    return padded, lengths, torch.cat(targets), target_lengths


class SelfAttention(nn.Module):
    def __init__(self, dimension: int, heads: int):
        super().__init__()
        if dimension % heads:
            raise ValueError("dimension must be divisible by heads")
        self.heads = heads
        self.head_dimension = dimension // heads
        self.scale = self.head_dimension ** -0.5
        self.query = nn.Linear(dimension, dimension)
        self.key = nn.Linear(dimension, dimension)
        self.value = nn.Linear(dimension, dimension)
        self.output = nn.Linear(dimension, dimension)

    def forward(self, values, padding_mask):
        batch = values.size(0)
        length = values.size(1)
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
    def __init__(self, dimension: int, heads: int, feedforward: int):
        super().__init__()
        self.attention_norm = nn.LayerNorm(dimension)
        self.attention = SelfAttention(dimension, heads)
        self.feedforward_norm = nn.LayerNorm(dimension)
        self.feedforward = nn.Sequential(
            nn.Linear(dimension, feedforward),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(feedforward, dimension),
        )
        self.dropout = nn.Dropout(0.1)

    def forward(self, values, padding_mask):
        values = values + self.dropout(self.attention(self.attention_norm(values), padding_mask))
        return values + self.dropout(self.feedforward(self.feedforward_norm(values)))


class GujaratiTransformerCtc(nn.Module):
    def __init__(
        self,
        input_size: int,
        output_size: int,
        dimension: int = 192,
        layers: int = 4,
        heads: int = 4,
        feedforward: int = 512,
        max_frames: int = 64,
    ):
        super().__init__()
        self.embedding = nn.Embedding(input_size, dimension, padding_idx=0)
        self.position = nn.Embedding(max_frames, dimension)
        self.encoder = nn.ModuleList(
            TransformerBlock(dimension, heads, feedforward) for _ in range(layers)
        )
        self.final_norm = nn.LayerNorm(dimension)
        self.output = nn.Linear(dimension, output_size)

    def forward(self, roman_ids):
        repeated = torch.repeat_interleave(roman_ids, 2, dim=1)
        positions = torch.arange(repeated.shape[1], device=repeated.device).unsqueeze(0)
        encoded = self.embedding(repeated) + self.position(positions)
        padding_mask = repeated.eq(0)
        for block in self.encoder:
            encoded = block(encoded, padding_mask)
        return self.output(self.final_norm(encoded))


def validation_loss(model, loader, loss_fn, device) -> float:
    model.eval()
    total = 0.0
    with torch.no_grad():
        for inputs, input_lengths, targets, target_lengths in loader:
            inputs = inputs.to(device)
            targets = targets.to(device)
            logits = model(inputs)
            loss = loss_fn(
                logits.log_softmax(-1).transpose(0, 1),
                targets,
                input_lengths,
                target_lengths,
            )
            total += float(loss)
    return total / max(1, len(loader))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "models" / "artifacts" / "gu-transformer-ctc-v2")
    parser.add_argument("--train-limit", type=int, default=400_000)
    parser.add_argument("--epochs", type=int, default=6)
    parser.add_argument("--batch-size", type=int, default=192)
    parser.add_argument("--seed", type=int, default=29)
    parser.add_argument("--learning-rate", type=float, default=8e-4)
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    torch.manual_seed(args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    if args.export_only:
        metadata_path = args.output / "vocab.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            input_vocab = metadata["input_vocab"]
            output_vocab = metadata["output_vocab"]
        else:
            # Recovery export for a completed checkpoint uses the exact pair
            # universe that launched that checkpoint; new training filters below.
            pairs = load_pairs(args.train_limit, args.seed)
            train_pairs, validation_pairs = split_pairs(pairs)
            input_vocab = ["<pad>", "<unk>", *sorted(set("".join(roman for roman, _ in pairs)))]
            output_vocab = ["<blank>", *sorted(set("".join(native for _, native in pairs)))]
            metadata = {
                "version": 2,
                "model_version": "gu-transformer-ctc-v2",
                "architecture": "4-layer-transformer-encoder-ctc",
                "training_pairs": len(train_pairs),
                "validation_pairs": len(validation_pairs),
                "training_epochs": args.epochs,
                "benchmark_family_exclusion": True,
                "family_disjoint_validation": True,
                "short_input_oversampling": True,
                "roman_noise_augmentation": True,
                "input_vocab": input_vocab,
                "input_unk": input_vocab.index("<unk>"),
                "output_vocab": output_vocab,
                "training_digest": hashlib.sha256("\n".join(f"{r}\t{n}" for r, n in train_pairs).encode()).hexdigest(),
            }
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        model = GujaratiTransformerCtc(len(input_vocab), len(output_vocab))
        model.load_state_dict(torch.load(args.output / "gujarati_xlit.pt", map_location="cpu"))
    else:
        pairs = [pair for pair in load_pairs(args.train_limit, args.seed) if valid_gujarati_word(pair[1])]
        if not pairs:
            raise SystemExit("no training pairs")
        train_pairs, validation_pairs = split_pairs(pairs)
        input_vocab = ["<pad>", "<unk>", *sorted(set("".join(roman for roman, _ in pairs)))]
        output_vocab = ["<blank>", *sorted(set("".join(native for _, native in pairs)))]
        input_index = {char: index for index, char in enumerate(input_vocab)}
        output_index = {char: index for index, char in enumerate(output_vocab)}
        train_data = TransformerPairDataset(train_pairs, input_index, output_index, True, args.seed)
        validation_data = TransformerPairDataset(validation_pairs, input_index, output_index, False, args.seed)
        train_loader = DataLoader(
            train_data,
            batch_size=args.batch_size,
            shuffle=True,
            collate_fn=collate,
            num_workers=0,
        )
        validation_loader = DataLoader(
            validation_data,
            batch_size=args.batch_size,
            shuffle=False,
            collate_fn=collate,
            num_workers=0,
        )
        model = GujaratiTransformerCtc(len(input_vocab), len(output_vocab)).to(device)
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(1, args.epochs))
        loss_fn = nn.CTCLoss(blank=0, zero_infinity=True)
        best_loss = float("inf")
        for epoch in range(args.epochs):
            model.train()
            total = 0.0
            for step, (inputs, input_lengths, targets, target_lengths) in enumerate(train_loader, 1):
                inputs = inputs.to(device)
                targets = targets.to(device)
                optimizer.zero_grad(set_to_none=True)
                logits = model(inputs)
                loss = loss_fn(
                    logits.log_softmax(-1).transpose(0, 1),
                    targets,
                    input_lengths,
                    target_lengths,
                )
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                total += float(loss.detach())
                if step % 250 == 0:
                    print(json.dumps({"epoch": epoch + 1, "step": step, "loss": round(total / step, 4)}), flush=True)
            dev_loss = validation_loss(model, validation_loader, loss_fn, device)
            scheduler.step()
            print(json.dumps({"epoch": epoch + 1, "loss": round(total / max(1, len(train_loader)), 4), "validation_loss": round(dev_loss, 4)}), flush=True)
            if dev_loss < best_loss:
                best_loss = dev_loss
                torch.save(model.state_dict(), args.output / "gujarati_xlit.pt")
        model.load_state_dict(torch.load(args.output / "gujarati_xlit.pt", map_location=device))
        metadata = {
            "version": 2,
            "model_version": "gu-transformer-ctc-v2",
            "architecture": "4-layer-transformer-encoder-ctc",
            "training_pairs": len(train_pairs),
            "validation_pairs": len(validation_pairs),
            "training_epochs": args.epochs,
            "benchmark_family_exclusion": True,
            "family_disjoint_validation": True,
            "short_input_oversampling": True,
            "roman_noise_augmentation": True,
            "input_vocab": input_vocab,
            "input_unk": input_index["<unk>"],
            "output_vocab": output_vocab,
            "training_digest": hashlib.sha256("\n".join(f"{r}\t{n}" for r, n in train_pairs).encode()).hexdigest(),
        }
        (args.output / "vocab.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    model = model.cpu().eval()
    (args.output / "vocab.tsv").write_text(
        "input\t" + "\t".join(input_vocab) + "\n" +
        "output\t" + "\t".join(output_vocab) + "\n" +
        "version\t" + str(metadata["model_version"]) + "\n",
        encoding="utf-8",
    )
    sample = torch.ones((1, 12), dtype=torch.long)
    torch.onnx.export(
        model,
        sample,
        args.output / "gujarati_xlit.onnx",
        input_names=["roman_ids"],
        output_names=["logits"],
        dynamic_axes={"roman_ids": {0: "batch", 1: "roman_length"}, "logits": {0: "batch", 1: "frames"}},
        opset_version=17,
        dynamo=False,
    )
    from onnxruntime.quantization import QuantType, quantize_dynamic

    quantize_dynamic(
        str(args.output / "gujarati_xlit.onnx"),
        str(args.output / "gujarati_xlit.int8.onnx"),
        weight_type=QuantType.QInt8,
    )
    print(json.dumps({"output": str(args.output), "pairs": metadata["training_pairs"], "model_version": metadata["model_version"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
