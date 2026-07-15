#!/usr/bin/env python3
"""Compare prefix-beam CTC decoding with exhaustive path marginalization."""
from __future__ import annotations

import itertools
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.gujarati_ctc import (
    GujaratiCtcOnnx,
    ctc_prefix_beam_candidates,
    valid_gujarati_word,
    valid_roman_word,
)


def logadd(a: float, b: float) -> float:
    if not math.isfinite(a):
        return b
    if not math.isfinite(b):
        return a
    maximum = max(a, b)
    return maximum + math.log(math.exp(a - maximum) + math.exp(b - maximum))


def collapse(path: tuple[int, ...], vocab: list[str]) -> str:
    output: list[str] = []
    previous = -1
    for token in path:
        if token and token != previous:
            output.append(vocab[token])
        previous = token
    return "".join(output)


def main() -> int:
    for roman in ("yas", "o'brien", "sh+ri"):
        assert valid_roman_word(roman)
    for roman in ("", ".", "3.", "--", "a..b", "a b", "ગુજરાતી"):
        assert not valid_roman_word(roman)
    for native in ("યસ", "શ્રદ્ધા", "હું", "ૐ"):
        assert valid_gujarati_word(native)
    for native in ("", "ી", "્ય", "ક્", "ક્‍", "કિી", "latin", "બદલ�"):
        assert not valid_gujarati_word(native)
    rng = np.random.default_rng(17)
    logits = rng.normal(size=(4, 3))
    logits -= logits.max(axis=1, keepdims=True)
    log_probs = logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))
    vocab = ["<blank>", "ક", "ા"]
    exact: dict[str, float] = {}
    for path in itertools.product(range(len(vocab)), repeat=len(log_probs)):
        native = collapse(path, vocab)
        if not native:
            continue
        score = sum(float(log_probs[frame, token]) for frame, token in enumerate(path))
        exact[native] = logadd(exact.get(native, -math.inf), score)
    expected = sorted(exact.items(), key=lambda item: item[1], reverse=True)[:8]
    actual = ctc_prefix_beam_candidates(log_probs, vocab, count=8, beam_width=32)
    if [item.native for item in actual] != [native for native, _score in expected]:
        raise SystemExit(f"prefix mismatch: {actual} != {expected}")
    for item, (_native, score) in zip(actual, expected, strict=True):
        if abs(item.log_prob - score) > 1e-8:
            raise SystemExit(f"score mismatch for {item.native}: {item.log_prob} != {score}")
    print("CTC_PREFIX_BEAM_OK paths=81 top=8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
