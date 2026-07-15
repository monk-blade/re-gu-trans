# Gujarati transliteration model

- Architecture: Gujarati character transliteration, int8 ONNX
- Intended use: optional offline n-best generation for re-gu-trans
- Base/reference: AI4Bharat IndicXlit
- Runtime output: up to four Gujarati candidates with log probabilities
- Prohibited: telemetry, hosted inference, non-Gujarati output

## Evaluation

Fill with source-disjoint top-1/top-3/recall@6, length strata, latency, and
deterministic-core deltas before packaging.

## Licenses

Include IndicXlit MIT attribution, Aksharantar CC-BY/CC0 attribution, and
Dakshina CC BY-SA 4.0 attribution as applicable to the trained artifact.
