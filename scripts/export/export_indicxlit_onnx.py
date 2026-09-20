#!/usr/bin/env python3
"""Export the AI4Bharat IndicXlit fairseq checkpoint to the ONNX encoder/decoder
pair expected by models/indicxlit_onnx.py (indicxlit_encoder.onnx,
indicxlit_decoder_v2.onnx, vocab.json).

Must run under the venv with fairseq/torch (.venv-indicxlit).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import eval._fairseq_py311_compat  # noqa: E402  (must precede fairseq import)
import torch
import torch.nn as nn
from fairseq import checkpoint_utils

RELEASE_DIR = ROOT / "data" / "external" / "indicxlit" / "release"
# Not part of AI4Bharat's release zip (which ships only corpus-bin/ and
# transformer/); this is the fixed, alphabetically-sorted list of the 21
# target language codes from the checkpoint's own lang_pairs config, needed
# to load its multilingual dictionaries. Committed here since data/external/
# is gitignored.
LANG_LIST = Path(__file__).resolve().parent / "indicxlit_lang_list.txt"
OUT_DIR = ROOT / "models" / "artifacts" / "gu-indicxlit-v1"
LANG = "gu"


class EncoderWrapper(nn.Module):
    def __init__(self, encoder):
        super().__init__()
        self.encoder = encoder

    def forward(self, src_tokens: torch.Tensor) -> torch.Tensor:
        # src_lengths only feeds a has-padding check inside fairseq's encoder,
        # never an actual tensor op, so torch.onnx.export prunes it as an
        # unused input if passed in externally; compute it locally instead.
        src_lengths = torch.full((src_tokens.shape[0],), src_tokens.shape[1], dtype=torch.long)
        out = self.encoder(src_tokens, src_lengths=src_lengths)
        return out["encoder_out"][0]


class DecoderWrapper(nn.Module):
    def __init__(self, decoder):
        super().__init__()
        self.decoder = decoder

    def forward(self, prev_output_tokens: torch.Tensor, encoder_out_tensor: torch.Tensor) -> torch.Tensor:
        encoder_out = {
            "encoder_out": [encoder_out_tensor],
            "encoder_padding_mask": [],
            "encoder_embedding": [],
            "encoder_states": [],
            "src_tokens": [],
            "src_lengths": [],
        }
        logits, _extra = self.decoder(prev_output_tokens, encoder_out=encoder_out)
        return logits


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    models, cfg, task = checkpoint_utils.load_model_ensemble_and_task(
        [str(RELEASE_DIR / "transformer" / "indicxlit.pt")],
        arg_overrides={
            "data": str(RELEASE_DIR / "corpus-bin"),
            "lang_dict": str(LANG_LIST),
        },
    )
    model = models[0]
    model.eval()
    src_dict = task.source_dictionary
    tgt_dict = task.target_dictionary

    # Roman words are capped at 32 chars (see valid_roman_word); trace with a
    # sample at that ceiling so length-dependent caches baked in during
    # tracing (positional embeddings, the decoder's causal mask buffer) are
    # built large enough for any real input instead of getting frozen at
    # whatever smaller size a short sample would trigger.
    max_len = 32
    lang_token = f"__{LANG}__"
    sample_word = "a" * max_len
    sample_tokens = [lang_token, *sample_word]
    sample_ids = torch.tensor(
        [[src_dict.index(t) for t in sample_tokens] + [src_dict.eos()]], dtype=torch.long
    )

    encoder_wrapper = EncoderWrapper(model.encoder)
    encoder_wrapper.eval()
    with torch.no_grad():
        encoder_out_sample = encoder_wrapper(sample_ids)
    print("encoder_out shape", encoder_out_sample.shape)

    encoder_onnx_path = OUT_DIR / "indicxlit_encoder.onnx"
    torch.onnx.export(
        encoder_wrapper,
        (sample_ids,),
        str(encoder_onnx_path),
        input_names=["src_tokens"],
        output_names=["encoder_out"],
        dynamic_axes={
            "src_tokens": {0: "batch", 1: "src_len"},
            "encoder_out": {0: "src_len", 1: "batch"},
        },
        opset_version=14,
        do_constant_folding=True,
    )
    print("wrote", encoder_onnx_path)

    decoder_wrapper = DecoderWrapper(model.decoder)
    decoder_wrapper.eval()
    # prev_output_tokens grows to max_len + 1 (leading eos) during beam search.
    prev_sample = torch.tensor([[src_dict.eos()] * (max_len + 1)], dtype=torch.long)
    with torch.no_grad():
        logits_sample = decoder_wrapper(prev_sample, encoder_out_sample)
    print("decoder logits shape", logits_sample.shape)

    decoder_onnx_path = OUT_DIR / "indicxlit_decoder_v2.onnx"
    torch.onnx.export(
        decoder_wrapper,
        (prev_sample, encoder_out_sample),
        str(decoder_onnx_path),
        input_names=["prev_tokens", "encoder_out"],
        output_names=["logits"],
        dynamic_axes={
            "prev_tokens": {0: "batch", 1: "tgt_len"},
            "encoder_out": {0: "src_len", 1: "batch"},
            "logits": {0: "batch", 1: "tgt_len"},
        },
        opset_version=14,
        do_constant_folding=True,
    )
    print("wrote", decoder_onnx_path)

    vocab = {
        "src": list(src_dict.symbols),
        "tgt": list(tgt_dict.symbols),
        "special_tokens": {
            "bos": src_dict.bos(),
            "pad": src_dict.pad(),
            "eos": src_dict.eos(),
            "unk": src_dict.unk(),
        },
        "lang": LANG,
        "source": "AI4Bharat IndicXlit v1.0 (transformer, en->gu)",
    }
    vocab_path = OUT_DIR / "vocab.json"
    vocab_path.write_text(json.dumps(vocab, ensure_ascii=False, indent=2), encoding="utf-8")
    print("wrote", vocab_path)

    # Dynamic int8 quantization: the raw fp32 export is ~48MB (over the
    # model pack's 35MB budget) and roughly 2.5x slower per query on CPU
    # (measured: ~56ms vs ~21ms warm p50); quantizing in place keeps the
    # committed artifact directory holding only the files the plugin loads.
    from onnxruntime.quantization import QuantType, quantize_dynamic

    for path in (encoder_onnx_path, decoder_onnx_path):
        fp32_path = path.with_name(path.stem + ".fp32.onnx")
        path.rename(fp32_path)
        quantize_dynamic(str(fp32_path), str(path), weight_type=QuantType.QInt8)
        fp32_path.unlink()
        print("quantized", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
