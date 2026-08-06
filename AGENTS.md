# AGENTS.md — Akshar GU (`re-gu-trans`)

Instructions for coding agents and maintainers working in this repository.

## Project contract

Akshar GU is a Gujarati roman-to-script input method for Squirrel, Weasel,
Fcitx5-Rime, and ibus-rime. The package id is `re-gu-trans`; the Rime schema
id is `gujarati`. The current repository version is in `VERSION` (`2.9.0`),
while the schema and Plum recipe use the compatible `2.9` major/minor form.

The production engine is a librime-qjs translator and two qjs processors. It
combines an Apple-derived roman lexicon, weighted phonetic generation, native
Gujarati frequency/stem/attestation evidence, optional user learning, and an
optional offline neural model. It must remain usable without the neural model.

Read these before changing behavior:

- [README.md](./README.md) for the architecture and quick start.
- [USAGE.md](./USAGE.md) for user-visible menu and commit behavior.
- [GUIDE.md](./GUIDE.md) for installation, data sources, and model-pack setup.
- [docs/ecosystem-integration.md](./docs/ecosystem-integration.md) for Rime
  ecosystem and packaging integration notes.
- [.github/workflows/ci.yml](./.github/workflows/ci.yml) for the authoritative
  non-release quality gates.

## Non-negotiable constraints

- Do not fix ranking by adding per-word branches or hard-coded exception lists.
  Prefer lexicon weights, reusable fuzzy/ending rules, stem/morph generation,
  native evidence, and globally validated coefficients.
- Do not commit secrets, Apple private frameworks/binaries, Google Input Tools
  binaries, local proprietary captures, or the full Marisa dump
  `archive/apple-extracts/gu_unified_marisa_keys.txt`.
- Do not force-push, rewrite published history, or move active runtime files
  into `archive/` without updating every consumer.
- Keep the interactive hot path bounded: binary Trie lookups, a lattice beam of
  at most 64, bounded prefix results, and cheap native/stem rescoring. Optional
  components must fail open to deterministic core behavior unless the user sets
  `translator/neural_mode: required`.
- Release payloads are binary-Trie/qjs-only. Never ship the large
  `gu_lexicon_blob.json` or LM TSV fallback with a binary release payload, and
  never reintroduce a table dictionary dependency into the schema.
- Preserve licenses, provenance, checksums, and measured metrics when changing
  data or model artifacts.

## Runtime architecture

Source assets live under `rime/`; installation scripts copy qjs entry files to
the Rime user-directory root and mirror modules under `user-dir/js/`. Do not
add committed root-level runtime duplicates to this repository.

| Path | Responsibility |
| --- | --- |
| `rime/gujarati.schema.yaml` | qjs-only schema, processor order, menu and translator knobs |
| `rime/js/gujarati_translator.js` | Thin qjs translator entrypoint |
| `rime/js/engine.js` | Thin adapter re-exporting the public ranking API |
| `rime/js/ranking.js` | Production translator, candidate generation, rescoring, layout, learning hooks |
| `rime/js/ranking_primitives.js` | Candidate records, tier mapping, layout, policy/coefficient helpers |
| `rime/js/phonetic.js` | Transliteration grammar, weighted fuzzy lattice, alternate/ending forms |
| `rime/js/storage.js` | Sole runtime authority for lexicon, prefix, native evidence, emoji, and fallbacks |
| `rime/js/learning.js` | Learning v2 format, threshold, migration, atomic persistence helpers |
| `rime/js/selection_tracker_processor.js` | Observes numbered selections before Rime’s selector |
| `rime/js/commit_on_punct_processor.js` | Commits the highlighted candidate on unmodified Space, `.`, `,`, `;`, or `'` |
| `rime/js/runtime_capabilities.js` | qjs/Trie/runtime capability probe and diagnostics |
| `rime/js/neural.js` | Optional `env.transliterateNBest()` bridge and validation |
| `rime/js/ranking_policy.json` | Shared ranking, lattice, morphology, emoji, and model policy |
| `rime/js/ltr_coefficients.json` | Global feature coefficients; disabled unless separately gated |
| `rime/js/lm/` | Build-time unigram, stem, and attested native evidence inputs |
| `scripts/package/` | Payload staging, validation, qjs plugin builds, and OS packaging |
| `native/gujarati-model-plugin/` | Optional ONNX Runtime native bridge for the model pack |
| `models/` | Model training/export code, cards, manifests, and validated artifacts |
| `eval/` | Offline ranking, parity, learning, quality, benchmark, and Rime harness tests |
| `archive/` | Inactive Apple extracts, legacy table dictionaries, and research leftovers only |

### Rime processor order

The order in `rime/gujarati.schema.yaml` is functional:

- `qjs_processor@commit_on_punct_processor` must remain before `key_binder`,
  because default Rime bindings otherwise turn `period`/`comma` into paging.
- `qjs_processor@selection_tracker_processor` must remain before `selector`,
  because it observes numbered selection keys and lets the selector perform the
  actual commit.
- The schema must continue to use `qjs_translator@gujarati_translator` and
  must not declare `dictionary: gujarati` or a table translator.

`./scripts/sync_rime.sh` installs the two qjs entry files both at the user-dir
root and under `js/`, reloads the detected frontend when possible, and removes
fallback assets unless `ALLOW_TEXT_FALLBACK=1` is explicitly set. It may write
outside the repository; use `RIME_USER_DIR=/tmp/...` for isolated checks.

## Ranking and menu invariants

Candidate source and tier are separate concepts. Lower tier wins before score;
`candidate.quality` is assigned only after display layout.

1. Personalized preference (`TIER_PERSONALIZED`, after the learning threshold).
2. Strong exact lexicon/exception (`TIER_EXACT`).
3. Evidence pool (`TIER_DICT`): soft exact, fuzzy, stem-derived, attested
   phonetic, and other evidence-backed forms. Near-exact forms are hard exact
   only when the typed roman has no lexicon entry; otherwise they stay here.
4. Unattested raw phonetic (`TIER_PHONETIC`).
5. Latin echo (`TIER_LATIN`), prefix completion (`TIER_PREFIX`), and emoji
   (`TIER_EMOJI`) remain below Gujarati candidates.

Important policy details:

- A soft lexicon weight is positive and below `100`; it must never become hard
  exact merely because its numeric weight is high.
- Fuzzy, stem-derived, matra, postfix, inflection, and compound candidates are
  evidence-pool candidates, not hard `EXACT` candidates.
- Layout is Gujarati #1, Latin echo in the fixed #2 slot when enabled, up to
  the configured additional Gujarati candidates, then high-confidence emoji,
  remaining Gujarati candidates, and prefix candidates. The default menu cap
  is 6.
- Soft-fill must not override a strong Apple entry just because its native
  unigram is larger. Use source-aware evidence and transform cost.
- ASCII integers, decimals, URLs, emails, and host-like literals stay Latin.
- Keep the default phonetic grammar: inherent schwa between consonants,
  productive conjuncts, explicit virama with `+`, and Gujarati orthography
  normalization. Add reusable rules in `CONFUSION_MAP`, `ENDING_VARIANTS`,
  `isNearExactRomanSuffix`, or policy-owned morphology rather than word cases.
- The lattice beam is hard-gated at 64 by `eval/check_budgets.py`.

The optional model can add candidates through `env.transliterateNBest()`. In
`auto` mode its absence must preserve deterministic output; `off` disables it;
`required` must reject a missing or invalid model pack. Neural arbitration may
override a strong lexicon candidate only under the explicit policy margins in
`ranking_policy.json`.

Learning is deliberately narrow: numbered selections are observed by the
selection tracker, and the third explicit selection for a roman input promotes
the preferred native. Space/punctuation commits do not themselves create a
learning event. Persistence requires qjs `env.writeFileAtomic`; there is no
`saveFile` or unrestricted global-write fallback. The user file is
`gujarati.user-learning.json` in the Rime user directory and is not a repository
artifact.

## Data and asset pipeline

Treat `rime/js/gu_lexicon_blob.json` as the build-time lexicon mirror and the
single qjs input for Trie generation. `data/gu_lexicon_blob.json` is its data
mirror. The Apple distillation path in `scripts/distill_apple_lexicon.py` can
consume local/private extracts and writes the tracked lexicon, exceptions,
training rows, phonetic rules, and qjs blob; do not run it expecting missing
private inputs to be reproducible in CI.

The native evidence path is:

```text
local/cached sources
  -> scripts/build_gu_word_freq.py
  -> rime/js/lm/{unigram.tsv,stems.json,attested.json}
  -> scripts/build_qjs_tries.py --bin --exceptions
  -> lexicon.trie.bin, prefix.trie.bin, native_lm.trie.bin
```

Source roles are intentionally different: Apple/proprietary and spell/dataset
sources can provide attestation; corpus sources provide counts; Aksharantar and
AI4Bharat soft sources provide unigram/soft-fill evidence but must not silently
be promoted to attested or strong exact. `scripts/filter_lexicon_quality.py`
removes sentence-like, overlong, and redundant soft forms. `ingest_aksharantar`
and `ingest_dakshina` exclude the frozen test roman split when used for soft
fill.

External downloads and local caches belong under `data/external/`, which is
ignored. Rebuild-only large files include `data/quality/unique_gu_words.tsv`,
text Trie dumps, eval summaries, and `dist/`. Do not hand-edit generated binary
Tries, LM outputs, or quality reports; change their source/script and rebuild.

When changing a data source or split, preserve the leakage contract:

```bash
python3 scripts/build_eval_splits.py                 # only when rebuilding splits
python3 scripts/check_lexicon_leakage.py
python3 scripts/build_qjs_tries.py --bin --exceptions
```

Do not regenerate and commit `data/splits/held_out_gold.jsonl` casually. It is
the frozen CI-safe evaluation sample; rebuild it only when intentionally
changing the evaluation manifest and document the reason.

## Development and verification

Python 3 and Node.js are required for normal offline work. CI uses Python 3.12,
Node 22, and installs `marisa-trie`, `onnxruntime`, and `numpy`. `marisa-trie`
is required to generate binary assets. A full real-host run additionally needs
a built librime tree, the patched librime-qjs plugin, a C++17 compiler, and a
deployer; it is not equivalent to the offline Node tests.

### Fast checks after JS/schema/ranking changes

Run the smallest relevant set first:

```bash
python3 scripts/build_qjs_tries.py --bin --exceptions
python3 eval/rank_offline.py
node eval/ranking_primitives_test.js
node eval/neural_bridge_test.js
python3 eval/learning_v2_test.py
node eval/learning_integration_runner.mjs
node eval/storage_runtime_test.js
node eval/runtime_capabilities_test.js
python3 eval/binary_text_parity.py
python3 scripts/check_version_sync.py
```

For user-visible smoke, inspect the first candidate for `jamin`, `favshe`,
`poshatu`, `ketli`, `padi`, and `chalshe`; verify Space and `.`/`,` commit the
highlighted candidate; verify `2026` and `2.9` remain ASCII. Check the Rime log
for `loaded plugin: qjs` and the `$qjs$ ... trie binary loaded` messages when a
real host is available.

### Full offline quality gates

The workflow is authoritative, but this is the useful local sequence after
installing its Python/Node dependencies:

```bash
python3 scripts/check_lexicon_leakage.py
python3 scripts/build_qjs_tries.py --bin --exceptions
python3 eval/rank_offline.py
python3 eval/apple_integrity.py
python3 eval/held_out_agree.py
python3 eval/gold_agree.py
python3 eval/apple_class_reference.py
node eval/neural_bridge_test.js
python3 eval/ctc_decoder_test.py
node eval/ranking_primitives_test.js
python3 eval/emoji_quality.py
python3 eval/apple_class_benchmark.py --stress 10000
python3 eval/neural_model_benchmark.py
python3 eval/menu_baseline_check.py
python3 eval/check_budgets.py
python3 scripts/check_version_sync.py
python3 eval/learning_v2_test.py
node eval/learning_integration_runner.mjs
node eval/storage_runtime_test.js
node eval/runtime_capabilities_test.js
python3 eval/binary_text_parity.py
python3 eval/ablation_check.py
python3 train/ltr/train_coefficients.py
python3 eval/held_out_diag.py
python3 eval/bench_production.py
python3 eval/release_quality_report.py
```

Most eval scripts write ignored JSON summaries. A failed gate is evidence to
investigate, not a reason to loosen a threshold or add an input-specific rule.

### Real librime and package checks

`eval/rime_harness.sh` stages a clean binary payload and, when
`REQUIRE_RIME_DEPLOYER=1` and `RIME_BUILD_ROOT` are supplied, verifies menus,
Latin placement, numbered learning, atomic persistence, runtime capabilities,
and query p95. Use the patched plugin built by the repository scripts. The
file-level checks can run without a full Rime build:

```bash
./scripts/package/clean_deploy_check.sh
./scripts/package/stage_payload.sh /tmp/re-gu-trans-payload generic
./scripts/package/validate_payload.sh /tmp/re-gu-trans-payload
```

Release packaging requires binary Tries and pins librime-qjs `v1.3.0` with
librime `1.16.1`. `scripts/package/validate_archive.sh` extracts a built
`.zip`, `.deb`, `.rpm`, or `.pkg`, validates the binary-only payload, and
checks the packaged plugin. Keep the staged payload under 70 MB. Release CI
also builds and validates the optional `gu-transformer-ctc-v3` model pack,
which must include the native plugin, ONNX Runtime, model/card/manifest,
licenses, and checksums; the model pack is not required for core typing.

## Editing and change discipline

- Make small, focused changes. Runtime behavior generally belongs in
  `rime/js/*.js` or `rime/gujarati.schema.yaml`; ranking policy belongs in
  `rime/js/ranking_policy.json` when it is shared with eval.
- Keep comments short and explain policy/reasoning rather than restating code.
- Update tests, fixtures, policy, or docs when a user-visible ranking/layout
  contract changes. Do not update only a generated eval summary.
- After JS/schema/data changes that affect the installed IME, rebuild relevant
  assets and run `./scripts/sync_rime.sh` when live local verification is
  intended. Prefer `RIME_USER_DIR=/tmp/...` when the user did not ask to alter
  their installed Rime configuration.
- Do not edit `rime/gujarati.schema.yaml` in a user installation to customize
  behavior; use `gujarati.custom.yaml` patches based on the sample.
- Keep `rime/js/storage.js` as the sole asset-loading authority. New runtime
  data must have both a release/binary path and a clearly bounded dev fallback,
  or be optional and fail open.
- Before changing `VERSION`, run `python3 scripts/check_version_sync.py` and
  update the schema/package metadata intentionally.
- Use `apply_patch` for source edits. Inspect `git status` before and after;
  preserve unrelated user changes. Never use destructive git cleanup to make a
  test pass.

## Sensitive and archived material

`archive/apple-extracts/` and `archive/tools/` may be required as local inputs
for reproducibility work, but they are not runtime dependencies or release
payloads. `archive/legacy-rime/` contains retired table dictionaries and JS;
do not resurrect them under `rime/`. Local model training data, Apple captures,
private probe output, and external downloads must stay in ignored locations.

When in doubt, verify the consumer graph with `rg` before renaming, deleting,
or archiving a file, and consult the workflow/package validators before
changing a release asset contract.
