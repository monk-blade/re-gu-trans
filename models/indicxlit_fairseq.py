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
    def __init__(self, release_dir: str | Path, lang: str = "gu", beam_size: int = 8, device: str = "cpu"):
        root = Path(release_dir)
        models, cfg, task = checkpoint_utils.load_model_ensemble_and_task(
            [str(root / "transformer" / "indicxlit.pt")],
            arg_overrides={
                "data": str(root / "corpus-bin"),
                "lang_dict": str(LANG_LIST),
            },
        )
        self.device = torch.device(device)
        for model in models:
            model.eval()
            model.to(self.device)
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
        src = self._encode(roman).to(self.device)
        sample = {
            "net_input": {
                "src_tokens": src.unsqueeze(0),
                "src_lengths": torch.tensor([src.numel()], device=self.device),
            }
        }
        self.generator.beam_size = beam_width
        with torch.no_grad():
            hypotheses = self.generator.generate(self.models, sample, prefix_tokens=None)
        return self._collect_hypotheses(hypotheses[0], count)

    def nbest_batch(
        self, romans: list[str], count: int = 4, beam_width: int = 8
    ) -> list[list[Candidate]]:
        """Batched form of nbest(): one generator.generate() call for the
        whole list instead of one call per roman. Left-pads to match
        fairseq's TranslationTask convention (left_pad_source=True) so the
        encoder's padding mask lines up the same way single-item encoding
        (an unpadded, single-row batch) implicitly does.

        Only throughput should differ from calling nbest() per item -- the
        caller is expected to spot-check that (see
        scripts/generate_indicxlit_pseudolabels_v5.py's startup check).
        """
        if not romans:
            return []
        count = max(1, min(8, int(count)))
        beam_width = max(count, min(12, int(beam_width)))
        left_pad = bool(getattr(self.task.cfg, "left_pad_source", True))
        pad_idx = self.src_dict.pad()

        encoded = [self._encode(roman) for roman in romans]
        lengths = torch.tensor([t.numel() for t in encoded], dtype=torch.long)
        max_len = int(lengths.max().item())
        batch = torch.full((len(encoded), max_len), pad_idx, dtype=torch.long)
        for row, tokens in enumerate(encoded):
            n = tokens.numel()
            if left_pad:
                batch[row, max_len - n :] = tokens
            else:
                batch[row, :n] = tokens
        batch = batch.to(self.device)
        lengths = lengths.to(self.device)

        sample = {"net_input": {"src_tokens": batch, "src_lengths": lengths}}
        self.generator.beam_size = beam_width
        with torch.no_grad():
            hypotheses = self.generator.generate(self.models, sample, prefix_tokens=None)
        return [self._collect_hypotheses(row_hypotheses, count) for row_hypotheses in hypotheses]

    def _collect_hypotheses(self, hypotheses, count: int) -> list[Candidate]:
        results: list[Candidate] = []
        seen: set[str] = set()
        for hypo in hypotheses:
            text = self.tgt_dict.string(hypo["tokens"], bpe_symbol=None, escape_unk=True).replace(" ", "")
            if not text or text in seen:
                continue
            seen.add(text)
            results.append(Candidate(native=text, log_prob=float(hypo["score"])))
            if len(results) >= count:
                break
        return results
