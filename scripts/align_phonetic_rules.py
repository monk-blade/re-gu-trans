#!/usr/bin/env python3
"""Merge Apple gu-Mappings into gujarati_translator.js consonant/vowel tables."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "rime" / "gujarati_translator.js"
RULES = ROOT / "data" / "gu_phonetic_rules.json"

# Map Apple roman keys -> which JS table + preferred glyph
# We inject APPLE_PREFERRED overlays used by transliterate when present.

HEADER = '''
// ---------------------------------------------------------------------------
// Apple gu-Mappings preferred overlays (distilled)
// First listed glyph is preferred when generating phonetic candidates.
// ---------------------------------------------------------------------------
'''


def main() -> None:
    rules = json.loads(RULES.read_text(encoding="utf-8"))
    # Build JS object of lowercase digraph/letter -> preferred gujarati
    preferred = {}
    for key, vals in rules.items():
        if not key or not key[0].islower():
            continue  # skip acronym A-Z mappings
        if not vals:
            continue
        preferred[key] = vals[0]

    js_obj_lines = ["const APPLE_PREFERRED = {"]
    for k in sorted(preferred.keys(), key=lambda x: (-len(x), x)):
        v = preferred[k]
        js_obj_lines.append(f"  '{k}': '{v}',")
    js_obj_lines.append("}")
    block = HEADER + "\n".join(js_obj_lines) + "\n"

    text = JS.read_text(encoding="utf-8")
    # Remove previous injection if re-run
    text = re.sub(
        r"\n// ---------------------------------------------------------------------------\n// Apple gu-Mappings preferred overlays[\s\S]*?\nconst APPLE_PREFERRED = \{[\s\S]*?\n\}\n",
        "\n",
        text,
    )

    # Align a few known digraphs in CONSONANTS / VOWEL tables directly
    replacements = {
        # ensure chh exists (already), add Apple-style 'c' secondary note via APPLE_PREFERRED
    }
    # Insert after CONSONANTS block closing
    marker = "const WORD_DICT = {"
    if marker not in text:
        raise SystemExit("WORD_DICT marker not found")
    if "const APPLE_PREFERRED" not in text:
        text = text.replace(marker, block + "\n" + marker)

    # Patch tokenize to try APPLE_PREFERRED longest-match first — inject helper before tokenize
    helper = '''
function applePreferredToken(input, i) {
  // Longest-match against APPLE_PREFERRED keys
  let best = null
  let bestLen = 0
  const slice = input.slice(i)
  for (const key of Object.keys(APPLE_PREFERRED)) {
    if (key.length > bestLen && slice.startsWith(key)) {
      best = key
      bestLen = key.length
    }
  }
  if (!best) return null
  return { key: best, value: APPLE_PREFERRED[best], len: bestLen }
}

'''
    if "function applePreferredToken" not in text:
        text = text.replace("function tokenize(input)", helper + "function tokenize(input)")

    JS.write_text(text, encoding="utf-8")
    print(f"aligned rules: {len(preferred)} preferred keys -> {JS}")


if __name__ == "__main__":
    main()
