# Optional Gujarati neural model pack

The core IME does not require a model. A distributable model pack must contain:

- `indicxlit_encoder.onnx` and `indicxlit_decoder_v2.onnx`
- `vocab.json`
- `librime-gujarati-model` for the target platform
- `model-card.md`, `training-manifest.json`, `LICENSES/`, and `SHA256SUMS`

The companion plugin exposes `env.transliterateNBest(roman, limit)` to QJS and
returns `{native, logProb, modelVersion}` records. `translator/neural_mode: auto`
falls back exactly to the deterministic engine if that capability is absent.

No placeholder model is shipped. The staging script rejects missing, oversized,
or undocumented artifacts so a package cannot claim neural support without an
actual tested model and runtime.

The current release model is `indicxlit-fairseq-v1.0`: AI4Bharat's IndicXlit
transformer (en→gu), exported from its released fairseq checkpoint to a
dynamic-int8-quantized ONNX encoder/decoder pair with
`scripts/export/export_indicxlit_onnx.py`. Unlike the single-pass CTC models
below it is a seq2seq architecture and requires autoregressive beam search
(`native/gujarati-model-plugin`), which is meaningfully slower per query in
exchange for higher accuracy — see `eval/indicxlit_ab_summary.json` for the
measured tradeoff. The earlier compact CTC line (`gu-transformer-ctc-v3`, `v2`,
`v1`) remains available as a faster, lower-accuracy alternative and as
reproducibility baselines; train it with
`python3 models/train_gujarati_transformer_v3.py`.
