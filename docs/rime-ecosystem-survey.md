# Rime / Indic IME ecosystem survey

Notes from surveying GitHub Rime configs and Indic transliteration projects relevant to **re-gu-trans** (2026-07).

## Finding

There is **no mature upstream Gujarati Rime schema** in [rime/plum](https://github.com/rime/plum) (Chinese-centric). We remain the primary Rime+qjs Gujarati roman→script package. Neighbor projects still provide packaging patterns and data we can reuse.

## Sources

| Source | Type | Adopt / defer / reject |
|--------|------|------------------------|
| [iDvel/rime-ice](https://github.com/iDvel/rime-ice) | Production Rime config | **Adopt:** plum recipes, `*.custom.yaml` patches only, low-priority custom phrases |
| [rime/plum](https://github.com/rime/plum) | Schema installer | **Adopt:** recipe install path alongside `sync_rime.sh` |
| [HuangJian/librime-qjs](https://github.com/HuangJian/librime-qjs) | Plugin host | **Adopted** (already required) |
| [hchunhui/librime-lua](https://github.com/hchunhui/librime-lua) | Scripting | **Defer:** qjs covers processors/translators; Lua filters later if needed |
| [rime/librime-predict](https://github.com/rime/librime-predict) / octagram | Next-word LM | **Defer** until unigram/attested path is enough |
| [keymanapp … itrans_gujarati](https://github.com/keymanapp/keyboards/tree/master/release/itrans/itrans_gujarati) | Phonetic ITRANS | **Defer (bounded):** digraph diff only; never replace Apple lexicon |
| [daivajnanam/lipika-ime](https://github.com/daivajnanam/lipika-ime) | macOS Indic IME | **Defer:** multi-scheme UI toggle |
| [AI4Bharat/IndicXlit](https://github.com/AI4Bharat/IndicXlit) + [Aksharantar](https://huggingface.co/datasets/ai4bharat/Aksharantar) | Translit model + parallel data | **Adopt data:** soft-fill OOV roman→native + native freq; **reject** full transformer in hot path |
| [shankarmishra/openhinglish](https://github.com/shankarmishra/openhinglish) | Hinglish lexicons | **Defer:** SMS/abbrev gazetteer needs GU-specific data first |

## Phonetic rule sources (IME ranking)

Scalable roman→GU rules in `rime/gujarati_translator.js` / `eval/rank_offline.py` (no per-word baking):

- **ISO 15919 / LOC GU** — homorganic anusvara (`n`/`m` before stop → `ં`)
- **ITRANS / Keyman GU / Quillpad** — `M`→`ં`, `sh`/`Sh`, geminate via virama, `v`/`w`
- **IndicXlit** — dictionary rescoring; Aksharantar soft-fill at low weight only
- **MS Indic Phonetic** — schwa-default between consonants; productive conjuncts only

Eval harness: `python3 eval/apple_agree.py` then `python3 eval/cluster_apple_disagree.py`.

## Non-negotiables (unchanged)

- No per-word hand-baked roman→script exceptions for ranking fixes
- Proprietary Google Input Tools / Apple assets: **local distill only** — never commit or redistribute binaries / full Marisa dumps
- Apple lexicon weights win over soft-fill when both exist
- `table_translator` must not outrank qjs for common words (see historical `jamin` bug)
- Aksharantar natives boost **unigram** only; they do **not** auto-join `attested` (spell/wiki/IME quality floors)

## Related in-repo

- Recipe: [`recipes/re-gu-trans.recipe.yaml`](../recipes/re-gu-trans.recipe.yaml) + [`scripts/install_recipe.sh`](../scripts/install_recipe.sh)
- Sample patch: [`rime/gujarati.custom.yaml.sample`](../rime/gujarati.custom.yaml.sample)
- Unique-quality set: [`data/quality/unique_gu_stats.json`](../data/quality/unique_gu_stats.json) — [`scripts/build_gu_word_freq.py`](../scripts/build_gu_word_freq.py) + [`scripts/extract_proprietary_gu_natives.py`](../scripts/extract_proprietary_gu_natives.py)
- Aksharantar soft-fill (OOV only): [`scripts/ingest_aksharantar_gu.py`](../scripts/ingest_aksharantar_gu.py)
