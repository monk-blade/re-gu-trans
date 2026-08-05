# Optional Gujarati neural model pack

The core IME does not require a model. A distributable model pack must contain:

- `gujarati_xlit.int8.onnx`
- `librime-gujarati-model` for the target platform
- `model-card.md`, `training-manifest.json`, `LICENSES/`, and `SHA256SUMS`

The companion plugin exposes `env.transliterateNBest(roman, limit)` to QJS and
returns `{native, logProb, modelVersion}` records. `translator/neural_mode: auto`
falls back exactly to the deterministic engine if that capability is absent.

No placeholder model is shipped. The staging script rejects missing, oversized,
or undocumented artifacts so a package cannot claim neural support without an
actual tested model and runtime.

The current release model is `gu-transformer-ctc-v3`: a compact distilled
character Transformer with a CTC head. Train the larger CUDA teacher and then
the student with `python3 models/train_gujarati_transformer_v3.py`; the v2
trainer and legacy GRU-CTC v1 remain available as reproducibility baselines.
