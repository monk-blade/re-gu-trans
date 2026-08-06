# Akshar GU Transformer-CTC v3

Gujarati-only character Transformer for optional offline n-best generation.

- Architecture: configurable-transformer-encoder-ctc-distilled
- Training pairs: 982,805, with family-disjoint validation
- Robustness: short-input oversampling and bounded Roman-noise augmentation
- Training: family-disjoint validation with CUDA AMP; distilled=True
- Quantization: dynamic int8 ONNX
- Model size: 4,203,190 bytes
- Telemetry/network inference: none

## Measured results

On the committed 2,500-word held-out suite, model-only top-1 is
67.28% and recall is 89.84%. The production
hybrid reaches 73.28% top-1 and 90.8% recall@6.
Warm ONNX Runtime P95 is 4.939 ms.

## Safety and limitations

The runtime rejects punctuation, numeric, mixed-script, malformed Unicode, and
invalid Gujarati syllable outputs before candidates enter the menu. This remains
a word-level model; it does not perform sentence segmentation or next-word prediction.
