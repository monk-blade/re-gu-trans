# Akshar GU IndicXlit v1.0

AI4Bharat's IndicXlit transformer (en→gu direction), exported from its
released fairseq checkpoint to a quantized ONNX encoder/decoder pair for
offline n-best generation.

- Architecture: transformer-seq2seq-beam-search (6 encoder + 6 decoder
  layers, 256-dim, 4 attention heads), autoregressive beam search
  (beam width 8, max 32 decode steps, early-stopped once no live beam can
  beat the current top candidates)
- Source: AI4Bharat IndicXlit v1.0 released checkpoint (MIT License)
- Quantization: dynamic int8 ONNX (encoder 6.1 MB, decoder 8.3 MB)
- Export: `scripts/export/export_indicxlit_onnx.py`
- Telemetry/network inference: none

## Measured results

On the committed 2,500-word held-out suite, this model reaches 76.84% top-1,
94.08% top-3, and 97.64% recall@6 — a meaningful accuracy gain over the
compact `gu-transformer-ctc-v3` line it replaces (67.28% / 86.96% / 89.84%
model-only). The tradeoff is latency: warm p50 is 21.4ms and p95 is 46.1ms
per query (native plugin, ONNX Runtime 1.23.2, single intra-op thread),
versus ~2-5ms for the single-pass CTC model, because seq2seq beam search
requires up to 32 sequential decoder calls per candidate instead of one
forward pass. See `eval/indicxlit_ab_summary.json` for the side-by-side
comparison that motivated this tradeoff.

## Safety and limitations

The native plugin rejects punctuation, numeric, mixed-script, malformed
Unicode, and invalid Gujarati syllable outputs before candidates enter the
menu. This remains a word-level model; it does not perform sentence
segmentation or next-word prediction. Beam search early-stopping is a
heuristic pruning rule (comparing raw, pre-length-penalty scores) rather than
an exhaustive search, so in rare cases a lower-ranked candidate that would
have won under full search may be dropped — this is a latency/quality
tradeoff accepted for interactive typing, not a correctness guarantee gap.
