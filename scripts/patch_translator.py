#!/usr/bin/env python3
"""Patch gujarati_translator.js: lexicon blob load, Apple priority, ONNX ranker client."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "rime" / "gujarati_translator.js"

LEXICON_BLOCK = r'''
// ---------------------------------------------------------------------------
// Distilled Apple lexicon / exceptions (loaded from JSON blob)
// ---------------------------------------------------------------------------

const LEXICON_BLOB_PATHS = [
  'gu_lexicon_blob.json',
  'js/gu_lexicon_blob.json',
  '~/Library/Rime/gu_lexicon_blob.json',
]

let APPLE_EXCEPTIONS = new Map()
let APPLE_LEXICON = new Map()
let LEXICON_LOADED = false

function loadLexiconBlob() {
  if (LEXICON_LOADED) return
  LEXICON_LOADED = true
  const paths = LEXICON_BLOB_PATHS.map(resolveUserPath)
  const text = readFileTextFromPaths(paths)
  if (!text) {
    console.log('$qjs$ lexicon blob missing; using WORD_DICT only')
    return
  }
  try {
    const data = JSON.parse(text)
    if (data.exceptions) {
      for (const [k, v] of Object.entries(data.exceptions)) {
        APPLE_EXCEPTIONS.set(String(k).toLowerCase(), v)
        DICT_TRIE.insert(String(k).toLowerCase(), v)
      }
    }
    if (data.lexicon) {
      let n = 0
      for (const [k, v] of Object.entries(data.lexicon)) {
        const key = String(k).toLowerCase()
        APPLE_LEXICON.set(key, v)
        if (!DICT_TRIE.findExact(key)) {
          DICT_TRIE.insert(key, v)
        }
        n += 1
      }
      console.log('$qjs$ lexicon loaded entries=' + n + ' exceptions=' + APPLE_EXCEPTIONS.size)
    }
  } catch (e) {
    console.error('$qjs$ lexicon parse error:', e.message)
  }
}

'''

ONNX_BLOCK = r'''
// ---------------------------------------------------------------------------
// Local ONNX ranker client (Unix socket via external helper)
// Never blocks typing: timeout / failure falls back to n-gram scores.
// ---------------------------------------------------------------------------

const ONNX_DEFAULT_SOCK = '~/Library/Rime/run/gu_ranker.sock'
const ONNX_CACHE = new Map()
const ONNX_CACHE_LIMIT = 400

function onnxCacheGet(key) {
  if (!ONNX_CACHE.has(key)) return null
  return ONNX_CACHE.get(key)
}

function onnxCacheSet(key, value) {
  if (ONNX_CACHE.size >= ONNX_CACHE_LIMIT) {
    const first = ONNX_CACHE.keys().next().value
    ONNX_CACHE.delete(first)
  }
  ONNX_CACHE.set(key, value)
}

function rankWithOnnx(input, candTexts, prev, env) {
  const enable = getEnvBool(env, 'translator/onnx_enable', true)
  if (!enable || !candTexts || candTexts.length === 0) return null
  const cacheKey = input + '||' + prev + '||' + candTexts.join('\u0001')
  const cached = onnxCacheGet(cacheKey)
  if (cached) return cached

  // librime-qjs may expose system() or not; try best-effort helper CLI.
  const helper = getEnvString(env, 'translator/onnx_helper', 'gu_ranker_client')
  const sock = resolveUserPath(getEnvString(env, 'translator/onnx_socket', ONNX_DEFAULT_SOCK))
  const timeoutMs = getEnvNumber(env, 'translator/onnx_timeout_ms', 3)
  if (typeof system !== 'function' && typeof os === 'undefined') {
    return null
  }

  const payload = JSON.stringify({ input: input, cands: candTexts, prev: prev || '', timeout_ms: timeoutMs })
  // Write temp request via helper stdin protocol: gu_ranker_client --sock PATH --json PAYLOAD
  try {
    let out = null
    if (typeof system === 'function') {
      // system() returns exit code only in many embeds; prefer os.exec if present
      out = null
    }
    if (typeof os !== 'undefined' && typeof os.exec === 'function') {
      // QuickJS os.exec is not always available; skip
      out = null
    }
    // Pipe through a tiny sync helper that prints JSON scores
    if (typeof std !== 'undefined' && std.popen) {
      const cmd = helper + ' --sock ' + JSON.stringify(sock) + ' --stdin'
      const pipe = std.popen(cmd, 'w+')
      if (pipe) {
        pipe.puts(payload)
        pipe.close(false) // keep read side? depends on impl
      }
    }
    // Fallback: look for precomputed scores file written by sidecar watcher (optional)
    const scorePath = resolveUserPath('~/Library/Rime/run/last_scores.json')
    // Direct TCP/unix not available in qjs sandbox — call helper that reads argv
    if (typeof std !== 'undefined' && std.popen) {
      const escaped = payload.replace(/'/g, "'\\''")
      const cmd = helper + ' --sock ' + sock + " --json '" + escaped + "'"
      const pipe = std.popen(cmd, 'r')
      if (pipe) {
        out = pipe.readAsString()
        pipe.close()
      }
    }
    if (!out) return null
    const parsed = JSON.parse(out)
    const scores = parsed.scores || parsed
    if (!Array.isArray(scores) || scores.length !== candTexts.length) return null
    onnxCacheSet(cacheKey, scores)
    return scores
  } catch (e) {
    return null
  }
}

function getEnvString(env, key, fallback) {
  try {
    if (env && env.engine && env.engine.schema && env.engine.schema.config) {
      const config = env.engine.schema.config
      if (typeof config.get_string === 'function') {
        return config.get_string(key) || fallback
      }
      if (typeof config.getString === 'function') {
        return config.getString(key) || fallback
      }
    }
  } catch (e) {
    return fallback
  }
  return fallback
}

'''

TRANSLATE_METHOD = r'''
  translate(input, segment, env) {
    try {
      if (!input || input.length === 0) {
        return []
      }

      loadLexiconBlob()

      const enableUserLm = getEnvBool(env, 'translator/enable_user_lm', true)
      LM_WEIGHTS.unigram = getEnvNumber(env, 'translator/lm_unigram_weight', LM_WEIGHTS.unigram)
      LM_WEIGHTS.bigram = getEnvNumber(env, 'translator/lm_bigram_weight', LM_WEIGHTS.bigram)
      LM_WEIGHTS.user = getEnvNumber(env, 'translator/lm_user_weight', LM_WEIGHTS.user)
      TRIGRAM_WEIGHT = getEnvNumber(env, 'translator/lm_trigram_weight', TRIGRAM_WEIGHT)
      const prevWords = getContextPrevWords(env)
      const prevWord = prevWords.length > 0 ? prevWords[prevWords.length - 1] : ''
      const candidates = []
      const seen = new Set()
      const lower = input.toLowerCase()

      // Apple-like priority:
      // 1) exceptions (100)
      // 2) lexicon exact (95)
      // 3) lexicon prefix (90)
      // 4) phonetic (80)

      const exc = APPLE_EXCEPTIONS.get(lower) || APPLE_EXCEPTIONS.get(input)
      if (exc && !seen.has(exc)) {
        candidates.push(new Candidate('gujarati', segment.start, segment.end, exc, input, 100))
        seen.add(exc)
      }

      const lexExact = APPLE_LEXICON.get(lower) || DICT_TRIE.findExact(lower) || DICT_TRIE.findExact(input)
      if (lexExact && !seen.has(lexExact)) {
        candidates.push(new Candidate('gujarati', segment.start, segment.end, lexExact, input, 95))
        seen.add(lexExact)
      }

      const altForms = generateAlternateForms(input)
      for (const form of altForms) {
        const exact = APPLE_LEXICON.get(form.toLowerCase()) || DICT_TRIE.findExact(form)
        if (exact && !seen.has(exact)) {
          candidates.push(new Candidate('gujarati', segment.start, segment.end, exact, input, 95))
          seen.add(exact)
        }
      }

      if (input.length >= 2) {
        const prefixMatches = DICT_TRIE.findPrefixMatches(lower, 16)
        for (const value of prefixMatches) {
          if (!seen.has(value)) {
            candidates.push(new Candidate('gujarati', segment.start, segment.end, value, input, 90))
            seen.add(value)
          }
        }
      }

      const gujarati = transliterate(input)
      if (gujarati && gujarati !== input && !seen.has(gujarati)) {
        candidates.push(new Candidate('gujarati', segment.start, segment.end, gujarati, input, 80))
        seen.add(gujarati)
      }

      if (candidates.length === 0) return []

      // Base n-gram scores
      const scored = candidates.map((candidate, index) => {
        const isPhonetic = candidate.text === gujarati
        const score = scoreCandidateWithContext(candidate.text, prevWords, isPhonetic)
        // quality prior from Apple-like tiers
        const tierBoost = (candidate.quality || 0) / 100
        return { candidate, score: score + tierBoost, index }
      })

      // Optional ONNX rescoring of top candidates
      const topForOnnx = scored.slice().sort((a, b) => b.score - a.score).slice(0, 8)
      const onnxScores = rankWithOnnx(
        lower,
        topForOnnx.map(x => x.candidate.text),
        prevWord,
        env
      )
      if (onnxScores) {
        const onnxWeight = getEnvNumber(env, 'translator/onnx_weight', 1.2)
        for (let i = 0; i < topForOnnx.length; i++) {
          topForOnnx[i].score += onnxWeight * Number(onnxScores[i] || 0)
        }
      }

      scored.sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score
        return a.index - b.index
      })

      const sortedCandidates = scored.map(item => item.candidate)

      if (sortedCandidates.length > 0) {
        recordUserChoice(USER_LM_DEFAULT_PATH, sortedCandidates[0].text, prevWord, enableUserLm)
      }

      return sortedCandidates

    } catch (e) {
      console.error('$qjs$ translate error:', e.message)
      return []
    }
  }
'''


def main() -> None:
    text = JS.read_text(encoding="utf-8")

    # Ensure lexicon block once (after DICT_TRIE population)
    if "function loadLexiconBlob" not in text:
        marker = "for (const [key, value] of Object.entries(WORD_DICT)) {\n  DICT_TRIE.insert(key, value)\n}"
        if marker not in text:
            raise SystemExit("DICT_TRIE init marker not found")
        text = text.replace(marker, marker + "\n" + LEXICON_BLOCK)

    if "function rankWithOnnx" not in text:
        # insert before Rime Translator section
        anchor = "// ---------------------------------------------------------------------------\n// Rime Translator"
        if anchor not in text:
            raise SystemExit("Rime Translator anchor not found")
        text = text.replace(anchor, ONNX_BLOCK + "\n" + anchor)

    # Replace translate method body
    pattern = re.compile(
        r"  translate\(input, segment, env\) \{[\s\S]*?\n  \}\n\}",
        re.M,
    )
    if not pattern.search(text):
        raise SystemExit("translate method not found")
    text = pattern.sub(TRANSLATE_METHOD.rstrip() + "\n}", text, count=1)

    # Constructor should preload lexicon
    text = text.replace(
        "constructor(env) {\n    console.log('$qjs$ gujarati translator init')\n  }",
        "constructor(env) {\n    console.log('$qjs$ gujarati translator init')\n    loadLexiconBlob()\n  }",
    )

    JS.write_text(text, encoding="utf-8")
    print(f"patched translator -> {JS}")


if __name__ == "__main__":
    main()
