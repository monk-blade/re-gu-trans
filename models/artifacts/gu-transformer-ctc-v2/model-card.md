# Akshar GU Transformer-CTC v2

Gujarati-only character Transformer for optional offline n-best generation.

- Architecture: 4-layer-transformer-encoder-ctc
- Training pairs: 392,078, with family-disjoint validation
- Robustness: short-input oversampling and bounded Roman-noise augmentation
- Quantization: dynamic int8 ONNX
- Model size: 1,543,415 bytes
- Telemetry/network inference: none

## Measured results

On the committed 2,500-word held-out suite, model-only top-1 is
50.52% and recall is 78.76%. The production
hybrid reaches 56.6% top-1 and 81.92% recall@6.
Warm ONNX Runtime P95 is 3.916 ms.

## Safety and limitations

The runtime rejects punctuation, numeric, mixed-script, malformed Unicode, and
invalid Gujarati syllable outputs before candidates enter the menu. This remains
a word-level model; it does not perform sentence segmentation or next-word prediction.
