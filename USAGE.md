# USAGE.md — Typing with Akshar GU

Daily use of **Akshar GU** (package id `re-gu-trans`): Gujarati roman→script input for Squirrel / Weasel / fcitx5-rime / ibus-rime.

Install first: **[GUIDE.md](./GUIDE.md)**.

## Select the keyboard

After install, enable your Rime frontend, then choose **Gujarati** / **Gujarati Transliteration**.

Deploy once (Squirrel menu ⟲ / Weasel Deploy) if candidates do not appear.

## Type roman, pick Gujarati

1. Type Gujarati words in Latin letters (`jamin`, `ketli`, `padi`).
2. The candidate menu appears as you type.
3. Confirm with **Space**, or punctuation: **`.` `,` `;` `'`**.

Arrow keys / number keys select another candidate when needed.

### Menu shape (schema 2.9+)

Typical order:

1. Best Gujarati word  
2. **Latin echo** (keep the roman spelling)  
3. More Gujarati alternatives  
4. Prefix completions  
5. Emoji (when enabled)

So slot **#2** is the intentional Latin keep-as-typed option — not a ranking bug.

## What stays ASCII

ASCII numbers and decimals stay ASCII: `2026`, `2.9`, `3.14`. Do not expect Gujarati digits when typing Western numerals.

## Smoke words

After deploy, try: `jamin`, `favshe`, `poshatu`, `ketli`, `padi`, then Space / `.` commit.

## Learning

When you repeatedly pick a candidate, the engine may promote it for that roman via `gujarati.user-learning.json` in your Rime user dir. To reset preferences, remove that file and redeploy.

## Sync from source (developers)

```bash
./scripts/sync_rime.sh
```

macOS user dir: `~/Library/Rime/`  
Windows: `%APPDATA%\Rime\`  
Linux: `~/.local/share/fcitx5/rime/` or `~/.config/ibus/rime/` (see GUIDE).

## Logs (troubleshooting)

Look for `loaded plugin: qjs` and lexicon/trie load lines in the Rime log (`$TMPDIR/rime.squirrel/rime.squirrel.INFO` on macOS).

More install detail: **[GUIDE.md](./GUIDE.md)**. Agent/dev conventions: **[AGENTS.md](./AGENTS.md)**.
