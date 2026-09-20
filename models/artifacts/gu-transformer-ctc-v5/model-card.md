# Akshar GU Transformer-CTC v5

Gujarati-only character Transformer for optional offline n-best generation.

- Architecture: configurable-transformer-encoder-ctc-sequence-distilled
- Training pairs: 994,199, with family-disjoint validation
- Robustness: short-input oversampling and bounded Roman-noise augmentation
- Training: family-disjoint validation with CUDA AMP; distilled=True
- Quantization: dynamic int8 ONNX
- Model size: 4,203,190 bytes
- Telemetry/network inference: none

Known limitation: reference word(s) yas rank(s) below #1 in this benchmark run (still present in the menu). Reviewed and accepted as an isolated tradeoff against the accuracy/latency gains below, not a systemic regression.

## Measured results

On the committed 2,500-word held-out suite, model-only top-1 is
70.32% and recall is 91.2%. The production
hybrid reaches 73.08% top-1 and 91.6% recall@6.
Warm ONNX Runtime P95 is 4.178 ms.

## Safety and limitations

The runtime rejects punctuation, numeric, mixed-script, malformed Unicode, and
invalid Gujarati syllable outputs before candidates enter the menu. This remains
a word-level model; it does not perform sentence segmentation or next-word prediction.
