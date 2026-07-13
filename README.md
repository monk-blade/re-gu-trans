# re-gu-trans — Apple-like Gujarati transliteration for Rime

Fast Gujarati roman→script IME for **Squirrel / Weasel / Fcitx5-Rime**, ranked like
Apple TransliterationIM — without baking individual word pairs.

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

## Quick start (packages)

1. Install a Rime frontend: [Squirrel](https://github.com/rime/squirrel/releases) (macOS), [Weasel](https://github.com/rime/weasel/releases) (Windows), or `fcitx5-rime` / `ibus-rime` (Linux).
2. Download the matching asset from [Releases](https://github.com/monk-blade/re-gu-trans/releases) (`.pkg` / `.zip` / `.deb` / `.rpm`).
3. Install, then select **Gujarati**. On Linux run `re-gu-trans-enable` once.

Schema **2.7** rescores with aspell-gu + hunspell attested words (plus Google/Indic freqs).

Try: `jamin`, `favshe`, `poshatu`, `ketli`. **Space** / **`.` `,` `;` `'`** commit the selection.

Full steps: **[GUIDE.md](./GUIDE.md)**.

## From source (macOS)

```bash
python3 scripts/build_gu_word_freq.py
./scripts/install_librime_qjs.sh
./scripts/sync_rime.sh
```

## Layout

| Path | Purpose |
|------|---------|
| `rime/gujarati_translator.js` | QuickJS translator |
| `rime/commit_on_punct_processor.js` | Commit on Space / punctuation |
| `rime/gujarati.schema.yaml` | Schema + engine wiring |
| `rime/gu_lexicon_blob.json` | Lexicon + weights for qjs |
| `rime/js/lm/` | `unigram.tsv` + `stems.json` |
| `scripts/package/` | Cross-platform package builders |
| `packaging/` | nfpm (deb/rpm) + Linux enable helper |
| `.github/workflows/release-packages.yml` | Tag → GitHub Release assets |
| `AGENTS.md` | Instructions for coding agents |

## Logs

`$TMPDIR/rime.squirrel/rime.squirrel.INFO` should show:

```text
loaded plugin: qjs
$qjs$ lexicon loaded entries=...
$qjs$ unigram loaded entries=...
```

See **[GUIDE.md](./GUIDE.md)** for macOS / Windows / Linux install.
See **AGENTS.md** for contributor/agent conventions.
