# re-gu-trans — Apple-like Gujarati transliteration for Rime + ONNX

Fast Gujarati roman→script IME for macOS **Squirrel/Rime**, ranked like Apple
TransliterationIM — without baking individual word pairs.

## Architecture

```
roman input
   ├─ 1. Exact / near-exact lexicon (Apple-distilled ~96k + weights)
   ├─ 2. Dict-validated phonetics (native unigram + stem morphology)
   ├─ 3. Latin echo
   ├─ 4. Raw phonetics (OOV fallback)
   └─ 5. Prefix completions (~suffix), weight-sorted
```

Fuzzy roman expansion (`sh↔Sh`, `t↔T`, `i↔ii`, `u↔un`, …) plus dictionary
rescoring (same idea as IndicXlit `rescore=True`).

| Source | Role |
|--------|------|
| Apple `UnifiedTransliteration-gu` distill | roman→native + weights |
| [Google i18n GU wordcounts](http://www.gstatic.com/i18n/corpora/wordcounts/gu.txt) | native frequency |
| [jishnu7/dictionaries](https://github.com/jishnu7/dictionaries) | Indic Keyboard priorities |
| Stem morphology | conjugations (e.g. ફાવ+શે) without listing every form |

## Quick start

```bash
# Rebuild native word freq + stems (Apple + Google + Indic caches)
python3 scripts/build_gu_word_freq.py

# One-time: install librime-qjs into system Squirrel (admin)
./scripts/install_librime_qjs.sh

# Sync schema + JS + lexicon into ~/Library/Rime and reload
./scripts/sync_rime.sh
```

Then select **Squirrel → Gujarati**. Try: `jamin`, `favshe`, `poshatu`, `ketli`.
**Space** / **`.` `,` `;` `'`** commit the selected candidate.

## Layout

| Path | Purpose |
|------|---------|
| `rime/gujarati_translator.js` | QuickJS translator |
| `rime/commit_on_punct_processor.js` | Commit on Space / punctuation |
| `rime/gujarati.schema.yaml` | Schema + engine wiring |
| `rime/gu_lexicon_blob.json` | Lexicon + weights for qjs |
| `rime/js/lm/` | `unigram.tsv` + `stems.json` |
| `scripts/` | Distill, freq build, sync, qjs install |
| `models/gu_ranker.onnx` | Optional ≤3ms ONNX rescoring |
| `AGENTS.md` | Instructions for coding agents |

## Logs

`$TMPDIR/rime.squirrel/rime.squirrel.INFO` should show:

```text
loaded plugin: qjs
$qjs$ lexicon loaded entries=...
$qjs$ unigram loaded entries=...
```

See **AGENTS.md** for contributor/agent conventions.
