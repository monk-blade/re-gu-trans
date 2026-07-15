#!/usr/bin/env python3
"""Train and export a benchmark-family-disjoint Gujarati character CTC model."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import unicodedata
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

ROOT = Path(__file__).resolve().parents[1]
PAIR_FILES = (
    ROOT / "data" / "external" / "aksharantar_gu_pairs.tsv",
    ROOT / "data" / "external" / "dakshina_gu_pairs.tsv",
)
BENCHMARKS = (
    ROOT / "data" / "splits" / "held_out_gold.jsonl",
    ROOT / "data" / "splits" / "apple_class_source_disjoint.jsonl",
)
ROMAN_RE = re.compile(r"^[a-zA-Z+'-]+$")
GUJARATI_RE = re.compile(r"^[\u0A80-\u0AFF\u200C\u200D]+$")


def roman_family(value: str) -> str:
    text = "".join(char for char in value.lower() if char.isascii() and (char.isalpha() or char in "+'"))
    return re.sub(r"([aeiou])\1+", r"\1", text.replace("w", "v"))


def exclusions() -> tuple[set[str], set[str]]:
    romans: set[str] = set()
    natives: set[str] = set()
    for path in BENCHMARKS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = json.loads(line)
            roman = row.get("roman") or row.get("input")
            native = row.get("native") or row.get("gold")
            if roman:
                romans.add(roman_family(str(roman)))
            if native:
                natives.add(unicodedata.normalize("NFC", str(native)))
    return romans, natives


def load_pairs(limit: int, seed: int) -> list[tuple[str, str]]:
    excluded_romans, excluded_natives = exclusions()
    pairs: dict[tuple[str, str], int] = {}
    for source_index, path in enumerate(PAIR_FILES):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            fields = line.split("\t")
            if len(fields) < 2:
                continue
            roman = fields[0].strip().lower()
            native = unicodedata.normalize("NFC", fields[1].strip())
            if not 1 <= len(roman) <= 32 or not 1 <= len(native) <= len(roman) * 2:
                continue
            if not ROMAN_RE.fullmatch(roman) or not GUJARATI_RE.fullmatch(native):
                continue
            if roman_family(roman) in excluded_romans or native in excluded_natives:
                continue
            frequency = int(fields[2]) if len(fields) > 2 and fields[2].isdigit() else 1
            pairs[(roman, native)] = max(pairs.get((roman, native), 0), frequency + source_index)
    ordered = list(pairs)
    random.Random(seed).shuffle(ordered)
    if limit > 0:
        ordered = ordered[:limit]
    return ordered


class PairDataset(Dataset):
    def __init__(self, pairs, input_index, output_index):
        self.rows = [
            (
                torch.tensor([input_index.get(char, 1) for char in roman], dtype=torch.long),
                torch.tensor([output_index[char] for char in native], dtype=torch.long),
            )
            for roman, native in pairs
        ]

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, index):
        return self.rows[index]


def collate(rows):
    inputs, targets = zip(*rows)
    lengths = torch.tensor([len(row) * 2 for row in inputs], dtype=torch.long)
    padded = nn.utils.rnn.pad_sequence(inputs, batch_first=True)
    target_lengths = torch.tensor([len(row) for row in targets], dtype=torch.long)
    return padded, lengths, torch.cat(targets), target_lengths


class GujaratiCtc(nn.Module):
    def __init__(self, input_size: int, output_size: int, embedding: int = 96, hidden: int = 128):
        super().__init__()
        self.embedding = nn.Embedding(input_size, embedding, padding_idx=0)
        self.encoder = nn.GRU(
            embedding, hidden, num_layers=2, batch_first=True, bidirectional=True, dropout=0.1
        )
        self.output = nn.Linear(hidden * 2, output_size)

    def forward(self, roman_ids):
        repeated = torch.repeat_interleave(self.embedding(roman_ids), 2, dim=1)
        encoded, _state = self.encoder(repeated)
        return self.output(encoded)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / ".cache" / "gujarati-ctc")
    parser.add_argument("--train-limit", type=int, default=400_000)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    torch.manual_seed(args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    if args.export_only:
        metadata = json.loads((args.output / "vocab.json").read_text(encoding="utf-8"))
        input_vocab = metadata["input_vocab"]
        output_vocab = metadata["output_vocab"]
        model = GujaratiCtc(len(input_vocab), len(output_vocab))
        model.load_state_dict(torch.load(args.output / "gujarati_xlit.pt", map_location="cpu"))
    else:
        pairs = load_pairs(args.train_limit, args.seed)
        if not pairs:
            raise SystemExit("no training pairs")
        input_vocab = ["<pad>", "<unk>", *sorted(set("".join(roman for roman, _ in pairs)))]
        output_vocab = ["<blank>", *sorted(set("".join(native for _, native in pairs)))]
        input_index = {char: index for index, char in enumerate(input_vocab)}
        output_index = {char: index for index, char in enumerate(output_vocab)}
        dataset = PairDataset(pairs, input_index, output_index)
        loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, collate_fn=collate)
        model = GujaratiCtc(len(input_vocab), len(output_vocab))
        optimizer = torch.optim.AdamW(model.parameters(), lr=2e-3, weight_decay=1e-5)
        loss_fn = nn.CTCLoss(blank=0, zero_infinity=True)
        model.train()
        for epoch in range(args.epochs):
            total = 0.0
            for step, (inputs, input_lengths, targets, target_lengths) in enumerate(loader, 1):
                optimizer.zero_grad(set_to_none=True)
                logits = model(inputs)
                loss = loss_fn(logits.log_softmax(-1).transpose(0, 1), targets, input_lengths, target_lengths)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                total += float(loss.detach())
                if step % 250 == 0:
                    print(json.dumps({"epoch": epoch + 1, "step": step, "loss": round(total / step, 4)}), flush=True)
            print(json.dumps({"epoch": epoch + 1, "loss": round(total / max(1, len(loader)), 4)}), flush=True)
        model.eval()
        torch.save(model.state_dict(), args.output / "gujarati_xlit.pt")
        metadata = {
            "version": 1,
            "architecture": "2-layer-bidirectional-gru-ctc",
            "training_pairs": len(pairs),
            "benchmark_family_exclusion": True,
            "input_vocab": input_vocab,
            "input_unk": input_index["<unk>"],
            "output_vocab": output_vocab,
            "training_digest": hashlib.sha256("\n".join(f"{r}\t{n}" for r, n in pairs).encode()).hexdigest(),
        }
        (args.output / "vocab.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    model.eval()
    (args.output / "vocab.tsv").write_text(
        "input\t" + "\t".join(input_vocab) + "\n" +
        "output\t" + "\t".join(output_vocab) + "\n",
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
    print(json.dumps({"output": str(args.output), "pairs": metadata["training_pairs"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
