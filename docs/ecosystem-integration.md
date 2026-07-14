# Ecosystem integration notes — Akshar GU (re-gu-trans)

## Plum (configuration only)

Recipe: [`recipes/re-gu-trans.recipe.yaml`](../recipes/re-gu-trans.recipe.yaml)

```bash
./scripts/install_recipe.sh
```

**Do not advertise `bash rime-install re-gu-trans` as a complete install.**  
`.trie.bin` assets are gitignored and are **not** available from a fresh source
checkout. Plum installs schema/JS config only. Official **Release packages** ship
the native **librime-qjs** plugin (with `writeFileAtomic`) and platform binary Tries.

Once binary Tries are published via a versioned release artifact, update the
[Plum](https://github.com/rime/plum) recipe to consume that release source.

## Frontends

Validate against current [Squirrel](https://github.com/rime/squirrel) and
[Weasel](https://github.com/rime/weasel) listed in the
[Rime ecosystem directory](https://hantang.github.io/rime-docs/list/).

## Deferred

- Sentence grammar ([Rime Ice](https://github.com/iDvel/rime-ice))
- Next-word prediction ([librime-predict](https://github.com/rime/librime-predict))

Defer until transliteration recall, explicit numbered learning, package
portability, and latency gates are green.

## Fixed defaults

QJS translator, word-level transliteration, Latin slot #2, Western numeric ASCII,
no per-word ranking exceptions, preferred GU after **3** numbered selections.
