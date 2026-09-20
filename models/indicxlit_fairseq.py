#!/usr/bin/env python3
"""Direct fairseq (PyTorch) adapter for the AI4Bharat IndicXlit checkpoint.

Used for the A/B benchmark against the in-house CTC models. Unlike
``indicxlit_onnx.py`` (which expects an already-exported ONNX encoder/decoder
pair) this loads the released fairseq checkpoint directly, so it works
without an ONNX export step. Requires ``fairseq``/``torch`` (see
``.venv-indicxlit``) and the ``eval._fairseq_py311_compat`` import shim.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import eval._fairseq_py311_compat  # noqa: F401  (must run before fairseq import)
import torch
from fairseq import checkpoint_utils


@dataclass(frozen=True)
class Candidate:
    native: str
    log_prob: float


LANG_LIST = Path(__file__).resolve().parent.parent / "scripts" / "export" / "indicxlit_lang_list.txt"


class IndicXlitFairseq:
    def __init__(self, release_dir: str | Path, lang: str = "gu", beam_size: int = 8):
        root = Path(release_dir)
        models, cfg, task = checkpoint_utils.load_model_ensemble_and_task(
            [str(root / "transformer" / "indicxlit.pt")],
            arg_overrides={
                "data": str(root / "corpus-bin"),
                "lang_dict": str(LANG_LIST),
            },
        )
        for model in models:
            model.eval()
        self.models = models
        self.task = task
        self.src_dict = task.source_dictionary
        self.tgt_dict = task.target_dictionary
        self.lang_token = f"__{lang}__"
        self.metadata = {"model_version": "indicxlit-fairseq-v1.0", "architecture": "transformer-seq2seq"}
        self.generator = task.build_generator(models, cfg.generation)

    def _encode(self, roman: str) -> torch.Tensor:
        tokens = [self.lang_token, *str(roman).strip().lower()]
        ids = [self.src_dict.index(token) for token in tokens]
        ids.append(self.src_dict.eos())
        return torch.tensor(ids, dtype=torch.long)

    def nbest(self, roman: str, count: int = 4, beam_width: int = 8) -> list[Candidate]:
        count = max(1, min(8, int(count)))
        beam_width = max(count, min(12, int(beam_width)))
        src = self._encode(roman)
        sample = {
            "net_input": {
                "src_tokens": src.unsqueeze(0),
                "src_lengths": torch.tensor([src.numel()]),
            }
        }
        self.generator.beam_size = beam_width
        with torch.no_grad():
            hypotheses = self.generator.generate(self.models, sample, prefix_tokens=None)
        results: list[Candidate] = []
        seen: set[str] = set()
        for hypo in hypotheses[0]:
            text = self.tgt_dict.string(hypo["tokens"], bpe_symbol=None, escape_unk=True).replace(" ", "")
            if not text or text in seen:
                continue
            seen.add(text)
            results.append(Candidate(native=text, log_prob=float(hypo["score"])))
            if len(results) >= count:
                break
        return results
