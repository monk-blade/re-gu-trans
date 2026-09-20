# Akshar GU Transformer-CTC v4

Gujarati-only character Transformer for optional offline n-best generation.

- Architecture: configurable-transformer-encoder-ctc-sequence-distilled
- Training pairs: 980,083, with family-disjoint validation
- Robustness: short-input oversampling and bounded Roman-noise augmentation
- Training: family-disjoint validation with CUDA AMP; distilled=True
- Quantization: dynamic int8 ONNX
- Model size: 4,203,191 bytes
- Telemetry/network inference: none

Known limitation: reference word(s) yas rank(s) below #1 in this benchmark run (still present in the menu). Reviewed and accepted as an isolated tradeoff against the accuracy/latency gains below, not a systemic regression.

## Measured results

On the committed 2,500-word held-out suite, model-only top-1 is
69.52% and recall is 90.04%. The production
hybrid reaches 72.64% top-1 and 90.92% recall@6.
Warm ONNX Runtime P95 is 3.575 ms.

## Safety and limitations

The runtime rejects punctuation, numeric, mixed-script, malformed Unicode, and
invalid Gujarati syllable outputs before candidates enter the menu. This remains
a word-level model; it does not perform sentence segmentation or next-word prediction.
