# re-gu-trans — Apple-like Gujarati transliteration for Rime

Fast Gujarati roman→script IME for **Squirrel / Weasel / Fcitx5-Rime**, ranked like
Apple TransliterationIM — without baking individual word pairs.

## Architecture (schema 2.9+)

```
roman input
   ├─ linguistic rank
   │    1. Strong exact / exceptions
   │    2. Evidence pool (soft exact, fuzzy, stem_derived, attested phonetics)
   │    3. Unattested raw phonetics
   │    4. Prefix
   │    5. Emoji
   └─ display layout: GU #1 → Latin #2 → remaining GU → prefix → emoji
```

Runtime assets under `rime/js/`: ESM modules + **binary Tries** (`*.trie.bin`).
Packages ship binaries + small JSON (exceptions/policy/emoji), not the multi‑MB lexicon blob.

## Quick start (packages)

1. Install a Rime frontend: [Squirrel](https://github.com/rime/squirrel/releases) (macOS), [Weasel](https://github.com/rime/weasel/releases) (Windows), or `fcitx5-rime` / `ibus-rime` (Linux).
2. Download the matching asset from [Releases](https://github.com/monk-blade/re-gu-trans/releases).
3. Install, then select **Gujarati**. On Linux run `re-gu-trans-enable` once.

Try: `jamin`, `favshe`, `poshatu`, `ketli`, `padi`. **Space** / **`.` `,` `;` `'`** commit.

Full steps: **[GUIDE.md](./GUIDE.md)**.

## From source (macOS)

```bash
python3 scripts/build_gu_word_freq.py
python3 scripts/build_qjs_tries.py --bin --exceptions
./scripts/install_librime_qjs.sh
./scripts/sync_rime.sh
```

## Layout

| Path | Purpose |
|------|---------|
| `rime/js/gujarati_translator.js` | Thin qjs translator (imports modules) |
| `rime/js/{ranking,phonetic,storage,learning}.js` | Authoritative ranking / lattice / Tries / learning |
| `rime/js/*.trie.bin` | Platform binary Tries (hot path) |
| `rime/gujarati.schema.yaml` | Schema 2.9+ (`latin_position: 2`) |
| `scripts/package/` | Stage payload + OS builders |
| `AGENTS.md` | Agent conventions |

## Logs

```text
loaded plugin: qjs
$qjs$ lexicon trie binary loaded
```

See **[GUIDE.md](./GUIDE.md)** and **[docs/rime-ecosystem-survey.md](./docs/rime-ecosystem-survey.md)**.
