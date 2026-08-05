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


ORTHOGRAPHIC_VARIANT_PENALTY = 0.5


def orthographic_variants(native: str):
    """Yield bounded Gujarati i-matra alternatives for CTC spelling noise.

    Public roman corpora use both long and short ``i`` spellings for related
    Gujarati forms. A single global matra swap improves recall without adding
    word-specific exceptions or changing the model vocabulary.
    """
    for index, char in enumerate(native):
        if char == "ી":
            yield native[:index] + "િ" + native[index + 1 :]


def valid_roman_word(value: str) -> bool:
    text = str(value or "")
    if not 1 <= len(text) <= 32:
        return False
    previous_separator = False
    for index, char in enumerate(text):
        letter = "a" <= char.lower() <= "z" and char.isascii()
        separator = char in "+'-"
        if not letter and not separator:
            return False
        if separator and (index == 0 or index + 1 == len(text) or previous_separator):
            return False
        previous_separator = separator
    return True


def valid_gujarati_word(text: str) -> bool:
    if not text:
        return False
    if text == "ૐ":
        return True
    have_base = consonant = matra = modifier = False
    after_virama = after_joiner = after_nukta = False
    for char in text:
        code = ord(char)
        independent = 0x0A85 <= code <= 0x0A94
        is_consonant = 0x0A95 <= code <= 0x0AB9 or code == 0x0AF9
        is_matra = 0x0ABE <= code <= 0x0ACC or 0x0AE2 <= code <= 0x0AE3
        is_modifier = 0x0A81 <= code <= 0x0A83
        if independent or is_consonant:
            if (after_virama or after_joiner) and not is_consonant:
                return False
            have_base = True
            consonant = is_consonant
            matra = modifier = after_virama = after_joiner = after_nukta = False
        elif code == 0x0ABC:
            if not have_base or not consonant or matra or modifier or after_virama or after_nukta:
                return False
            after_nukta = True
        elif code == 0x0ACD:
            if not have_base or not consonant or matra or modifier or after_virama:
                return False
            after_virama = True
            after_joiner = False
        elif code in (0x200C, 0x200D):
            if not after_virama or after_joiner:
                return False
            after_joiner = True
        elif is_matra:
            if not have_base or not consonant or matra or modifier or after_virama or after_joiner:
                return False
            matra = True
        elif is_modifier:
            if not have_base or modifier or after_virama or after_joiner:
                return False
            modifier = True
        else:
            return False
    return have_base and not after_virama and not after_joiner


def _logadd(*values: float) -> float:
    finite = [value for value in values if value != -math.inf]
    if not finite:
        return -math.inf
    maximum = max(finite)
    return maximum + math.log(sum(math.exp(value - maximum) for value in finite))


def ctc_prefix_beam_candidates(
    log_probs: np.ndarray,
    output_vocab: list[str],
    count: int = 4,
    beam_width: int = 8,
) -> list[Candidate]:
    width = max(count, min(32, int(beam_width)))
    beams: dict[tuple[int, ...], tuple[float, float]] = {(): (0.0, -math.inf)}
    for frame in log_probs:
        keep = min(width, len(frame))
        top = set(int(token) for token in np.argpartition(frame, -keep)[-keep:])
        top.add(0)
        expanded: dict[tuple[int, ...], tuple[float, float]] = {}

        def update(prefix: tuple[int, ...], blank: float = -math.inf, nonblank: float = -math.inf):
            old_blank, old_nonblank = expanded.get(prefix, (-math.inf, -math.inf))
            expanded[prefix] = (_logadd(old_blank, blank), _logadd(old_nonblank, nonblank))

        for prefix, (prob_blank, prob_nonblank) in beams.items():
            total = _logadd(prob_blank, prob_nonblank)
            update(prefix, blank=total + float(frame[0]))
            last = prefix[-1] if prefix else -1
            for token in top:
                if token == 0:
                    continue
                probability = float(frame[token])
                if token == last:
                    update(prefix, nonblank=prob_nonblank + probability)
                    update(prefix + (token,), nonblank=prob_blank + probability)
                else:
                    update(prefix + (token,), nonblank=total + probability)
        beams = dict(
            sorted(expanded.items(), key=lambda item: _logadd(*item[1]), reverse=True)[:width]
        )
    unique: dict[str, float] = {}
    for prefix, probabilities in beams.items():
        native = "".join(
            output_vocab[token] for token in prefix if token and token < len(output_vocab)
        )
        score = _logadd(*probabilities)
        if native and score > unique.get(native, -math.inf):
            unique[native] = score
    for native, score in list(unique.items()):
        for variant in orthographic_variants(native):
            if valid_gujarati_word(variant):
                unique[variant] = max(
                    unique.get(variant, -math.inf), score - ORTHOGRAPHIC_VARIANT_PENALTY
                )
    return [
        Candidate(native=native, log_prob=score)
        for native, score in sorted(unique.items(), key=lambda item: item[1], reverse=True)[:count]
    ]


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

    def _decode(self, prefix: tuple[int, ...]) -> str:
        return "".join(
            self.output_vocab[token]
            for token in prefix
            if token and token < len(self.output_vocab)
        )

    def nbest(self, roman: str, count: int = 4, beam_width: int = 8) -> list[Candidate]:
        if not valid_roman_word(roman):
            return []
        logits = self.session.run(None, {"roman_ids": self._input(roman)})[0][0]
        logits -= logits.max(axis=1, keepdims=True)
        log_probs = logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))
        width = max(count, min(32, int(beam_width)))
        candidates = ctc_prefix_beam_candidates(log_probs, self.output_vocab, width, beam_width)
        return [item for item in candidates if valid_gujarati_word(item.native)][:count]
