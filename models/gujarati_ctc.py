#!/usr/bin/env python3
"""Inference adapter for the compact Gujarati-only CTC transliterator."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort


@dataclass(frozen=True)
class Candidate:
    native: str
    log_prob: float


class GujaratiCtcOnnx:
    def __init__(self, model_dir: str | Path):
        root = Path(model_dir)
        self.metadata = json.loads((root / "vocab.json").read_text(encoding="utf-8"))
        self.input_index = {char: index for index, char in enumerate(self.metadata["input_vocab"])}
        self.output_vocab = self.metadata["output_vocab"]
        self.unk = int(self.metadata["input_unk"])
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(root / "gujarati_xlit.int8.onnx"), options, providers=["CPUExecutionProvider"]
        )

    def _input(self, roman: str) -> np.ndarray:
        ids = [self.input_index.get(char, self.unk) for char in str(roman).lower()]
        return np.asarray([ids or [self.unk]], dtype=np.int64)

    def _decode(self, path: tuple[int, ...]) -> str:
        output: list[str] = []
        previous = -1
        for token in path:
            if token and token != previous and token < len(self.output_vocab):
                output.append(self.output_vocab[token])
            previous = token
        return "".join(output)

    def nbest(self, roman: str, count: int = 4, beam_width: int = 8) -> list[Candidate]:
        logits = self.session.run(None, {"roman_ids": self._input(roman)})[0][0]
        logits -= logits.max(axis=1, keepdims=True)
        log_probs = logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))
        width = max(count, min(32, int(beam_width)))
        beams: dict[tuple[int, ...], float] = {(): 0.0}
        for frame in log_probs:
            top = np.argpartition(frame, -min(width, len(frame)))[-min(width, len(frame)):]
            expanded: dict[tuple[int, ...], float] = {}
            for path, score in beams.items():
                for token in top:
                    candidate = path + (int(token),)
                    value = score + float(frame[token])
                    old = expanded.get(candidate)
                    if old is None or value > old:
                        expanded[candidate] = value
            beams = dict(sorted(expanded.items(), key=lambda item: item[1], reverse=True)[:width])
        unique: dict[str, float] = {}
        for path, score in beams.items():
            native = self._decode(path)
            if native and score > unique.get(native, -math.inf):
                unique[native] = score
        return [
            Candidate(native=native, log_prob=score)
            for native, score in sorted(unique.items(), key=lambda item: item[1], reverse=True)[:count]
        ]
