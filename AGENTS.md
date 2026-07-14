# AGENTS.md — re-gu-trans

Guidance for coding agents working in this repository.

## Project

**re-gu-trans** is a macOS **Squirrel/Rime** Gujarati roman→script IME that aims to match Apple TransliterationIM quality:

- Distilled Apple lexicon (~96k roman→native pairs + weights)
- Phonetic generation with fuzzy roman confusions (`sh↔Sh`, `t↔T`, `i↔ii`, `u↔un`, …)
- Native-script word-frequency + stem rescoring (IndicXlit-style dictionary rescoring)
- QuickJS plugins via **librime-qjs** (`gujarati_translator.js`, `commit_on_punct_processor.js`)

User data live-sync target: `~/Library/Rime/` (never commit that directory).

## Non-negotiables

1. **No per-word baking** for ranking fixes. Prefer lexicon weights, fuzzy roman expansion, near-exact suffix promotion, and unigram/stem rescoring.
2. **Do not commit secrets**, Apple private binaries, or full Marisa dumps (`gu_unified_marisa_keys.txt` is gitignored).
3. **Do not force-push** or rewrite published history unless the user explicitly asks.
4. Keep the hot path fast: lexicon/trie lookups + cheap unigram/stem rescoring.

## Layout

| Path | Purpose |
|------|---------|
| `rime/gujarati.schema.yaml` | Schema 2.9+ (processors/translators/knobs; `latin_position: 2`) |
| `rime/js/gujarati_translator.js` | Thin qjs translator (Candidate/notifiers) |
| `rime/js/ranking.js` | Tiers, CandidateRecord, menu layout, LTR coeffs hook |
| `rime/js/phonetic.js` | Fuzzy + weighted lattice (beam≤64) |
| `rime/js/storage.js` | Binary Trie loaders (`lexicon/prefix/native_lm.trie.bin`) |
| `rime/js/learning.js` | `gujarati.user-learning.json` via `writeFileAtomic` only |
| `rime/js/commit_on_punct_processor.js` | Space / `.,;'` commit selected candidate |
| `rime/js/gu_lexicon_blob.json` | Build input; not required in release when bins ship |
| `rime/js/lm/` | Unigram/stems/attested build inputs |
| `scripts/sync_rime.sh` | Copy assets → Rime user dir + reload |
| `scripts/build_qjs_tries.py` | Emit text + platform `.trie.bin` |
| `scripts/package/` | Stage payload; build macOS/Windows/Linux packages |
| `vendor/librime-qjs/` | Pinned plugin + `writeFileAtomic` overlay |
| `GUIDE.md` | Install walkthrough |
| `.github/workflows/ci.yml` | PR/main gates (leakage, smoke, held-out, gold, budgets) |

## Candidate ranking contract

Linguistic order (lower tier wins), then **display layout**:

1. Strong exact / exception
2. Evidence pool — soft exact, fuzzy, **stem_derived (never hard EXACT)**, attested phonetics
3. Unattested raw phonetics
4. Prefix
5. Emoji

Display: Gujarati #1 → Latin echo #2 (`include_latin`, fixed slot) → remaining GU → prefix → emoji.
Assign `candidate.quality` **after** layout. Soft-fill never overrides Apple ≥100 by weight alone.

## Day-to-day commands

```bash
python3 scripts/build_gu_word_freq.py
./scripts/sync_rime.sh          # macOS ~/Library/Rime or Linux fcitx5/ibus dir
```

Install / Linux walkthrough: **[GUIDE.md](./GUIDE.md)**.
Ecosystem survey (Rime-ice, plum, Aksharantar, …): **[docs/rime-ecosystem-survey.md](./docs/rime-ecosystem-survey.md)**.

Schema processor order is critical for `.` commit: `commit_on_punct` must run **before** `key_binder` (default maps `period` → `Page_Down` when `has_menu`).

Ranking regression check (no Rime required):

```bash
python3 scripts/build_gu_word_freq.py   # aspell-gu + hunspell + Google/Indic
python3 scripts/ingest_aksharantar_gu.py --from-cache --max-soft 300000  # bare-stem OOV bands 75/80/85
python3 scripts/ingest_dakshina_gu_pairs.py --from-cache   # Dakshina roman↔GU soft stems
python3 scripts/extract_proprietary_gu_natives.py          # Google IME natives when available
python3 scripts/filter_lexicon_quality.py # drop residual soft postfix/long noise
python3 eval/rank_offline.py
python3 eval/apple_agree.py
python3 eval/soft_oov_agree.py
./scripts/install_recipe.sh             # or ./scripts/sync_rime.sh
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
