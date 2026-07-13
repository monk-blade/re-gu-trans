# AGENTS.md — re-gu-trans

Guidance for coding agents working in this repository.

## Project

**re-gu-trans** is a macOS **Squirrel/Rime** Gujarati roman→script IME that aims to match Apple TransliterationIM quality:

- Distilled Apple lexicon (~96k roman→native pairs + weights)
- Phonetic generation with fuzzy roman confusions (`sh↔Sh`, `t↔T`, `i↔ii`, `u↔un`, …)
- Native-script word-frequency + stem rescoring (IndicXlit-style dictionary rescoring)
- Optional local ONNX ranker over a Unix socket
- QuickJS plugins via **librime-qjs** (`gujarati_translator.js`, `commit_on_punct_processor.js`)

User data live-sync target: `~/Library/Rime/` (never commit that directory).

## Non-negotiables

1. **No per-word baking** for ranking fixes. Prefer lexicon weights, fuzzy roman expansion, near-exact suffix promotion, and unigram/stem rescoring.
2. **Do not commit secrets**, Apple private binaries, or full Marisa dumps (`gu_unified_marisa_keys.txt` is gitignored).
3. **Do not force-push** or rewrite published history unless the user explicitly asks.
4. Keep the hot path fast: lexicon/trie lookups + cheap rescoring; ONNX budget ≤ ~3ms and must fail open.

## Layout

| Path | Purpose |
|------|---------|
| `rime/gujarati.schema.yaml` | Schema (processors/translators/knobs) |
| `rime/gujarati_translator.js` | Main qjs translator |
| `rime/commit_on_punct_processor.js` | Space / `.,;'` commit selected candidate |
| `rime/gu_lexicon_blob.json` | `{exceptions,lexicon,weights}` for qjs |
| `rime/js/lm/unigram.tsv` | Native word frequencies |
| `rime/js/lm/stems.json` | Stem → frequency for morphology |
| `scripts/sync_rime.sh` | Copy assets → `~/Library/Rime` + reload Squirrel |
| `scripts/build_gu_word_freq.py` | Rebuild unigram/stems from Apple+Google+Indic |
| `scripts/distill_apple_lexicon.py` | Rebuild lexicon blob / dict from probe extracts |
| `scripts/install_librime_qjs.sh` | Install `librime-qjs.dylib` into Squirrel |
| `runtime/onnx_ranker/` | Socket ranker server/client |
| `models/gu_ranker.onnx` | Tiny ranker model |
| `data/` | Distill outputs + cached external wordcounts |

## Candidate ranking contract

Order (lower tier wins; Rime sorts by `Candidate.quality`):

1. **Exact / near-exact lexicon** (fuzzy roman queries + `poshatu`→`poshatun`-style weak suffixes)
2. **Dict-validated phonetics** (unigram or stem evidence)
3. **Latin echo**
4. **Raw phonetics**
5. **Prefix completions** (`~suffix`), weight-sorted

Always assign `candidate.quality` after sorting — Rime **ignores array order**.

## Day-to-day commands

```bash
# Rebuild frequency dictionaries (uses data/external caches when present)
python3 scripts/build_gu_word_freq.py

# Deploy to Squirrel user data + reload
./scripts/sync_rime.sh

# One-time plugin install (admin)
./scripts/install_librime_qjs.sh
```

Verify in `$TMPDIR/rime.squirrel/rime.squirrel.INFO`:

```text
$qjs$ lexicon loaded entries=...
$qjs$ unigram loaded entries=...
$qjs$ stems loaded entries=...
loaded plugin: qjs
```

Smoke tests after ranking changes: `jamin`, `favshe`, `poshatu`, `ketli`, then Space / `.` commit.

## Editing rules

- Prefer small, focused diffs in `rime/*.js` + `rime/gujarati.schema.yaml`.
- After JS/schema/data changes that affect the IME, run `./scripts/sync_rime.sh`.
- When extending fuzzy matching, put rules in `CONFUSION_MAP` / `ENDING_VARIANTS` / `isNearExactRomanSuffix` — not special-case word lists.
- Schema processor order matters: `qjs_processor@commit_on_punct_processor` must sit **before** `punctuator` / `speller` consumers that would eat Space/`.` .
- Keep comments short; explain *why* (ranking policy), not what the next line does.

## Out of scope / caution

- Reverse-engineering notes may reference Apple private frameworks; do not redistribute Apple assets.
- `.venv/` is local only.
- GitHub `gh` requires a valid login (`gh auth login` / `gh auth refresh`) before `gh repo create` / push.
