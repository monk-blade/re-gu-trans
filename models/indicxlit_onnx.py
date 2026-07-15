#!/usr/bin/env python3
"""Small ONNX Runtime adapter for the MIT IndicXlit encoder/decoder export."""
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


class IndicXlitOnnx:
    def __init__(self, model_dir: str | Path):
        root = Path(model_dir)
        options = ort.SessionOptions()
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.encoder = ort.InferenceSession(
            str(root / "indicxlit_encoder.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.decoder = ort.InferenceSession(
            str(root / "indicxlit_decoder_v2.onnx"), options, providers=["CPUExecutionProvider"]
        )
        self.vocab = json.loads((root / "vocab.json").read_text(encoding="utf-8"))
        self.src_index = {token: index for index, token in enumerate(self.vocab["src"])}
        self.special = self.vocab["special_tokens"]

    def _tokenize(self, roman: str) -> np.ndarray:
        tokens = ["__gu__", *str(roman).strip().lower()]
        unk = self.special["unk"]
        ids = [self.src_index.get(token, unk) for token in tokens]
        ids.append(self.special["eos"])
        return np.asarray([ids], dtype=np.int64)

    def _detokenize(self, tokens: tuple[int, ...]) -> str:
        output: list[str] = []
        for index, token_id in enumerate(tokens):
            if index == 0:
                continue
            if token_id == self.special["eos"]:
                break
            if token_id in {
                self.special["bos"],
                self.special["pad"],
                self.special["unk"],
            }:
                continue
            if 0 <= token_id < len(self.vocab["tgt"]):
                output.append(self.vocab["tgt"][token_id])
        return "".join(output).replace(" ", "")

    def nbest(self, roman: str, count: int = 4, beam_width: int = 4, max_len: int = 32) -> list[Candidate]:
        count = max(1, min(8, int(count)))
        beam_width = max(count, min(12, int(beam_width)))
        encoded = self.encoder.run(None, {"src_tokens": self._tokenize(roman)})[0]
        eos = int(self.special["eos"])
        beams: list[tuple[float, tuple[int, ...]]] = [(0.0, (eos,))]
        finished: list[tuple[float, tuple[int, ...]]] = []

        for _step in range(max_len):
            if not beams:
                break
            previous = np.asarray([tokens for _score, tokens in beams], dtype=np.int64)
            batch_encoder = np.repeat(encoded, len(beams), axis=1)
            logits = self.decoder.run(
                None, {"prev_tokens": previous, "encoder_out": batch_encoder}
            )[0][:, -1, :]
            logits -= logits.max(axis=1, keepdims=True)
            log_probs = logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))
            if previous.shape[1] <= 1:
                log_probs[:, eos] = -np.inf
            width = min(log_probs.shape[1], beam_width * 2)
            next_ids = np.argpartition(log_probs, -width, axis=1)[:, -width:]
            expanded: list[tuple[float, tuple[int, ...]]] = []
            for row, (score, tokens) in enumerate(beams):
                for token_id in next_ids[row]:
                    candidate = (score + float(log_probs[row, token_id]), tokens + (int(token_id),))
                    if int(token_id) == eos:
                        finished.append(candidate)
                    else:
                        expanded.append(candidate)
            expanded.sort(key=lambda item: item[0], reverse=True)
            beams = expanded[:beam_width]

        finished.extend(beams)
        scored = []
        for score, tokens in finished:
            length_penalty = math.pow((5 + max(1, len(tokens) - 1)) / 6, 1.0)
            scored.append((score / length_penalty, tokens))
        scored.sort(key=lambda item: item[0], reverse=True)
        results: list[Candidate] = []
        seen: set[str] = set()
        for score, tokens in scored:
            native = self._detokenize(tokens)
            if not native or native in seen:
                continue
            seen.add(native)
            results.append(Candidate(native=native, log_prob=score))
            if len(results) >= count:
                break
        return results
