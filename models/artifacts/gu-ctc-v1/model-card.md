# Akshar GU CTC v1

Gujarati-only character transliteration model for optional offline n-best generation.

- Architecture: two-layer bidirectional GRU with CTC output
- Training pairs: 200,000, sampled deterministically after benchmark-family exclusion
- Inputs: lowercase roman characters
- Outputs: Gujarati Unicode characters
- Quantization: dynamic int8 ONNX
- Model size: 1,908,649 bytes
- Telemetry/network inference: none

## Measured results

On the committed 2,500-word held-out suite, the production hybrid improved from
42.44% to 55.72% top-1 and from 52.24% to 79.16% recall@6. Model-only top-3 was
67.44%. Across 3,500 measured ONNX Runtime queries, warm P95 was 1.528 ms.

The model is an optional candidate generator. Deterministic Trie, morphology,
learning, and Latin-slot behavior remain authoritative when the model pack is
not installed.

## Limitations

This is a word-level model. It does not segment sentences or predict the next
word. Names and English loanwords remain less reliable than common Gujarati
words. Outputs must pass the runtime Gujarati Unicode validator.

