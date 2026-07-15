# Akshar GU

**Akshar GU** is a fast Gujarati roman→script IME for **Squirrel / Weasel / Fcitx5-Rime / ibus-rime**.  
Repository and package id: **`re-gu-trans`**.

It ranks candidates like Apple TransliterationIM — lexicon + fuzzy phonetics + native-script evidence — without baking per-word exceptions.

## Docs

| Doc | Audience |
|-----|----------|
| **[USAGE.md](./USAGE.md)** | Daily typing (menu, Space/`.` commit, Latin #2, numerals) |
| **[GUIDE.md](./GUIDE.md)** | Install from Releases or from source |
| **[AGENTS.md](./AGENTS.md)** | Contributors / coding agents |
| [docs/ecosystem-integration.md](./docs/ecosystem-integration.md) | Plum / Squirrel / Weasel / deferred Ice+predict |
| [docs/rime-ecosystem-survey.md](./docs/rime-ecosystem-survey.md) | Broader ecosystem survey |

## Quick start

1. Install a Rime frontend: [Squirrel](https://github.com/rime/squirrel/releases) (macOS), [Weasel](https://github.com/rime/weasel/releases) (Windows), or `fcitx5-rime` / `ibus-rime` (Linux).
2. Download the matching asset from [Releases](https://github.com/monk-blade/re-gu-trans/releases).
3. Install, then select **Gujarati**. On Linux run `re-gu-trans-enable` once.
4. Type: `jamin`, `favshe`, `poshatu`, `ketli`, `padi`. Confirm with **Space** or **`.` `,` `;` `'`**.

Full install steps: **[GUIDE.md](./GUIDE.md)**. Typing tips: **[USAGE.md](./USAGE.md)**.

## Architecture (schema 2.9+)

```
roman input
   ├─ linguistic rank
   │    1. Strong exact / exceptions
   │    2. Evidence pool (soft exact, fuzzy, stem_derived, attested phonetics)
   │    3. Unattested raw phonetics
   │    4. Prefix completion
   │    5. Confidence-scored emoji
   └─ display: GU #1 → Latin #2 → up to 2 GU → strong emoji → remaining/prefix
```

Runtime assets live under `rime/js/`: ESM modules + **binary Tries** (`*.trie.bin`).  
Release packages ship bins + small JSON (exceptions/policy/emoji), not multi‑MB intermediate dumps.

Inactive extracts and legacy table-dict leftovers sit in **`archive/`** (not loaded at runtime).

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
| `rime/js/gujarati_translator.js` | Thin qjs translator |
| `rime/js/{ranking,phonetic,storage,learning,neural}.js` | Ranking / lattice / Tries / learning / optional model bridge |
| `rime/js/*.trie.bin` | Platform binary Tries (hot path) |
| `rime/gujarati.schema.yaml` | Schema 2.9+ (`latin_position: 2`) |
| `scripts/package/` | Stage payload + OS builders |
| `archive/` | Unused / legacy snapshots only |
| `USAGE.md` | End-user typing guide |

## License

See [LICENSE](./LICENSE) and [NOTICE](./NOTICE). Do not redistribute Apple private frameworks or full Marisa dumps.
