// ranking.js — production candidate generation, rescoring, personalization, and layout.
// Authoritative public APIs re-exported via ranking.js / phonetic.js / engine.js.

import {
  layoutMenu as modLayoutMenu,
  generateCandidates as modGenerateCandidates,
  rankCandidates as modRankCandidates,
  makeCandidateRecord,
  TIER_PERSONALIZED,
  TIER_EXACT,
  TIER_DICT,
  TIER_PHONETIC,
  TIER_LATIN,
  TIER_PREFIX,
  TIER_EMOJI,
  TIER_MAX,
} from './ranking_primitives.js'
import {
  expandRomanLattice,
  DEFAULT_CONFUSION_PAIRS,
  DEFAULT_LATTICE,
  phoneticFormsForRoman,
  normalizeGujaratiOrthography,
  generateAlternateForms,
  isInternalVowelLengthExpansion,
  isNearExactRomanSuffix,
  withEndingVariants,
  ANUSVARA,
  endsWithConsonantWithImplicitA,
  isIndependentVowelToken,
} from './phonetic.js'
import {
  loadRuntimeStorage,
  trieFind,
  prefixSearch,
  nativeEvidenceLookup,
  nativeLmMax,
} from './storage.js'
import {
  emptyLearning,
  explicitCount,
  preferredNative,
  getLearningSession,
  initLearningSession,
  EXPLICIT_PROMOTION_THRESHOLD,
} from './learning.js'
import { logRuntimeCapabilities } from './runtime_capabilities.js'
import { neuralNBest } from './neural.js'

// Gujarati phonetic transliteration engine for Rime using librime-qjs
//
// Transliteration scheme (IAST-inspired, phonetic):
//   Vowels: a અ, aa આ, i ઇ, ee/ii ઈ, u ઉ, oo/uu ઊ, R ઋ, RR ૠ, E ઍ, e એ, ai ઐ,
//            O ઑ, o ઓ, au ઔ, aM અં, aH અઃ, oM ઓં
//   Consonants: k ક, kh ખ, g ગ, gh ઘ, ng ઙ,
//               c/ch ચ, chh છ, j જ, jh ઝ, ny ઞ,
//               T ટ, Th ઠ, D ડ, Dh ઢ, N ણ,
//               t ત, th થ, d દ, dh ધ, n ન,
//               p પ, ph/f ફ, b બ, bh ભ, m મ,
//               y ય, r ર, l લ, L ળ, v/w વ,
//               sh શ, Sh ષ, s સ, h હ,
//               x/ksh ક્ષ, gy જ્ઞ, dv દ્વ, z ઝ
//   Digits: 0 ૦, 1 ૧, 2 ૨, 3 ૩, 4 ૪, 5 ૫, 6 ૬, 7 ૭, 8 ૮, 9 ૯
//   Virama (halant): + forces explicit halant on preceding consonant
//
// Behavior:
//   - Consonant alone carries implicit short 'a'
//   - Consonant + vowel = consonant with corresponding matra
//   - Consonant followed by another consonant = first gets virama (્)
//   - '+' forces virama explicitly
//   - Arabic digits transliterate to Gujarati digits
//   - Unknown characters pass through unchanged (punctuation, spaces)
//   - Dictionary lookup for common Gujarati words (trie-backed for speed)


let APPLE_EXCEPTIONS = new Map()
const KNOWN_WORDS = new Set()

function nativeLexHit(roman) {
  return roman && RUNTIME ? trieFind(RUNTIME, roman) : null
}

function lexiconWeight(roman) {
  const hit = nativeLexHit(roman)
  return hit ? hit.weight : 0
}

const APPLE_LEXICON = {
  get(key) { const hit = nativeLexHit(key); return hit ? hit.native : undefined },
  has(key) { return !!nativeLexHit(key) },
}
const DICT_TRIE = {
  findExact(key) { const hit = nativeLexHit(key); return hit ? hit.native : null },
  findPrefixEntries(prefix, limit = 20) {
    const out = []
    for (const row of prefixSearch(RUNTIME, prefix, limit)) {
      const prefixKey = row.text || row.key || ''
      const info = row.info || row.value || ''
      for (const payload of String(info).split('\x1e')) {
        const parts = payload.split('\x1f')
        if (!parts[0]) continue
        out.push({ key: parts[2] || prefixKey || prefix, value: parts[0] })
        if (out.length >= limit) return out
      }
    }
    return out
  },
}


// ---------------------------------------------------------------------------
// Language model and personalization
// ---------------------------------------------------------------------------

const LM_WEIGHTS = {
  unigram: 0.6,
  user: 0.6,
}

// Keep in sync with scripts/build_gu_word_freq.py SUFFIXES
const GU_SUFFIXES = [
  'વાળાઓ', 'વાળીઓ', 'વાળું', 'વાળી', 'વાળા', 'વાળો',
  'ીઓ', 'ાઓ', 'ોને', 'ાને', 'ીને', 'ુંને',
  'માંથી', 'માં', 'થી', 'ની', 'નો', 'ના', 'ને', 'નું', 'નાં',
  'શે', 'શો', 'શું', 'ીશ', 'ીશું',
  '્યો', '્યા', '્યું',
  'તો', 'તા', 'તી', 'તું', 'તાં',
  'વું', 'વા', 'વાનું', 'વાની', 'વાના',
  'ે', 'ો', 'ા', 'ી', 'ું', 'ાં',
]

/** Soft NFC for GU natives (NFC may be unavailable in some qjs builds). */
function toNfc(text) {
  if (!text) return text
  try {
    if (typeof text.normalize === 'function') return text.normalize('NFC')
  } catch (e) { /* ignore */ }
  return text
}

/** Soft demotion for illegal GU combining piles (not a full syllable rejector). */
function guOrthographyPenalty(text) {
  if (!text) return 0
  let pen = 0
  const matra = /[\u0ABE-\u0ACC\u0AE2\u0AE3]/
  const virama = '\u0ACD'
  if (matra.test(text[0])) pen += 3.0
  for (let i = 0; i < text.length - 1; i++) {
    const a = text[i]
    const b = text[i + 1]
    if (a === virama && b === virama) pen += 2.5
    if (matra.test(a) && matra.test(b)) pen += 2.0
  }
  return pen
}

/** Native-dict / stem / spell-dict validity — IndicXlit-style rescoring signal. */
function dictionaryValidity(text) {
  if (!text) {
    return {
      score: 0,
      evidence: 0,
      unigram: 0,
      stem: 0,
      attested: false,
      spellOk: false,
      uniStrong: false,
      present: false,
    }
  }
  text = toNfc(text)
  const direct = nativeEvidence(text)
  const uni = direct.unigram
  let stemReal = direct.stem
  const spellOk = direct.attested
  const floor = nativeEvidenceFloor()
  let spellHit = spellOk ? floor : 0
  let stemHit = stemReal
  if (spellOk) stemHit = Math.max(stemHit, floor)
  for (const suffix of GU_SUFFIXES) {
    if (text.length <= suffix.length + 1 || !text.endsWith(suffix)) continue
    const stem = text.slice(0, -suffix.length)
    if (!stem) continue
    const ev = nativeEvidence(stem)
    stemHit = Math.max(stemHit, ev.unigram, ev.stem, ev.attested ? floor : 0)
    stemReal = Math.max(stemReal, ev.unigram > floor ? ev.unigram : 0, ev.stem)
    for (const ext of ['ે', 'ો', 'ા', 'ી', 'ું', 'વું', 'તું', 'વા', 'શે', 'શો']) {
      const formEv = nativeEvidence(stem + ext)
      stemHit = Math.max(
        stemHit,
        formEv.unigram,
        formEv.stem,
        formEv.attested ? floor : 0
      )
      stemReal = Math.max(
        stemReal,
        formEv.unigram > floor ? formEv.unigram : 0,
        formEv.stem
      )
    }
  }
  const uniStrong = uni > floor
  const evidence = Math.max(uni, stemHit, spellHit)
  // Artificial attested-floor membership alone is not strong dictionary evidence.
  const attested = uni > 0 || stemReal > 0 || (spellOk && uniStrong)
  let virama = 0
  for (const ch of text) if (ch === '\u0ACD') virama += 1
  const score =
    Math.log1p(uni) +
    Math.log1p(spellHit) * 0.35 +
    Math.log1p(stemHit) * (uni > 0 ? 0.35 : 0.7) -
    virama * 0.25 -
    guOrthographyPenalty(text)
  return {
    score: Math.max(0, Number.isFinite(score) ? score : 0),
    evidence,
    unigram: uni,
    stem: stemHit,
    attested,
    spellOk,
    uniStrong,
    present: !!direct.present,
  }
}

function nativeEvidence(text) {
  if (RUNTIME && (RUNTIME.mode === 'trie' || RUNTIME.mode === 'map')) {
    return nativeEvidenceLookup(RUNTIME, text)
  }
  return { unigram: 0, stem: 0, attested: false, present: false }
}

function nativeEvidenceFloor() {
  if (RUNTIME && RUNTIME.nativeLm) return Number(RUNTIME.nativeLm.floor) || 0
  return 50
}

function nativeEvidenceMax() {
  if (RUNTIME && (RUNTIME.mode === 'trie' || RUNTIME.mode === 'map')) {
    return nativeLmMax(RUNTIME)
  }
  return 1
}

function normalizedScore(count, max) {
  if (!count || !max) return 0
  return Math.log1p(count) / Math.log1p(max)
}

function userBoost(count) {
  if (!count) return 0
  return Math.min(LM_WEIGHTS.user * 1.5, Math.log1p(count) / 3.5)
}

/** Extra boost when user previously committed this native for this typed roman.
 * After threshold commits, personalized tier + ceiling boost. */
function userRomanBoost(typedRoman, native, threshold) {
  const pref = preferredNative(USER_LEARNING, typedRoman)
  if (pref && pref === native) return 80
  const c = explicitCount(USER_LEARNING, typedRoman, native)
  if (!c) return 0
  const thr = threshold || USER_LEARNING_THRESHOLD || EXPLICIT_PROMOTION_THRESHOLD
  if (c >= thr) return 80
  // Frequency/recency is tie-break only — never promotes before threshold
  return Math.min(4.0, 1.2 * Math.log1p(c))
}

let USER_LEARNING = emptyLearning()
let USER_LEARNING_THRESHOLD = EXPLICIT_PROMOTION_THRESHOLD
let USER_LEARNING_ENABLED = true
/** @type {object|null} sole storage runtime from loadRuntimeStorage */
let RUNTIME = null

function initRuntimeStorage(env) {
  const allowText =
    getEnvBool(env, 'translator/allow_text_fallback', false) ||
    (typeof globalThis !== 'undefined' && globalThis.__AKSHAR_ALLOW_TEXT_FALLBACK__ === true)
  RUNTIME = loadRuntimeStorage(env, {
    allowTextFallback: allowText,
    releaseMode: !allowText,
  })
  if (RUNTIME.mode === 'error') {
    console.error('$qjs$ storage init failed: ' + (RUNTIME.capabilities && RUNTIME.capabilities.error))
  }
  return RUNTIME
}



/** Soft-fill / weak lexicon weights must not outrank attested phonetics (Aksharantar=75). */
const LEXICON_STRONG_WEIGHT = 100

/**
 * Native is a longer morph of `baseNative` (આચાર → આચારાંગ / આડ → આડું).
 * Used to demote soft/exact morph steals over bare stems.
 */
function isNativeMorphExtension(baseNative, native) {
  if (!baseNative || !native || native === baseNative) return false
  if (!native.startsWith(baseNative)) return false
  if (native.length <= baseNative.length) return false
  return true
}

/**
 * True when `key` is `typed` with only ephemeral schwa 'a' inserted between consonants.
 * mne→mane is weak evidence; do not treat as TIER_EXACT.
 * a→aa lengthening (kyare→kyaare, avo→aavo) is NOT ephemeral — keep strong / exact.
 */
function isAInsertionOnly(typed, key) {
  if (!typed || !key || key === typed) return false
  if (key.length <= typed.length) return false
  let i = 0
  let j = 0
  let inserted = 0
  while (i < typed.length && j < key.length) {
    if (typed[i] === key[j]) {
      i += 1
      j += 1
      continue
    }
    if (key[j] === 'a') {
      // Extra a adjacent to an already-matched a is vowel lengthening, not schwa insert.
      if (j > 0 && key[j - 1] === 'a') return false
      j += 1
      inserted += 1
      continue
    }
    return false
  }
  if (i !== typed.length) return false
  while (j < key.length) {
    if (key[j] !== 'a') return false
    if (j > 0 && key[j - 1] === 'a') return false
    j += 1
    inserted += 1
  }
  return inserted > 0
}

/** IAST place-of-articulation pairs: dental ↔ retroflex (n/N, t/T, d/D, l/L). */
const IAST_PLACE_PAIR = {
  n: 'N', N: 'n', t: 'T', T: 't', d: 'D', D: 'd', l: 'L', L: 'l',
}

/** Map lexicon hit → tier. Soft / a-insertion fuzzy never get TIER_EXACT. */
function lexiconHitTier(source, weight, typedRoman, hitRoman) {
  const w = Number(weight) || 0
  const soft = w > 0 && w < LEXICON_STRONG_WEIGHT
  // Bare consonant: Apple soft-maps n→ણ etc. Keep DICT so IAST phonetics (ન/ત/…) compete.
  if (typedRoman && typedRoman.length === 1 && IAST_PLACE_PAIR[typedRoman]) {
    return TIER_DICT
  }
  if (source === 'strict' && !soft) return TIER_EXACT
  if (soft) return TIER_DICT
  // Digraph strip (vinash→vinas via sh→s) must not EXACT-steal over typed soft/long forms.
  if (source === 'fuzzy' && typedRoman && hitRoman && isDigraphStripFuzzy(typedRoman, hitRoman)) {
    return TIER_DICT
  }
  if (
    source === 'fuzzy' &&
    typedRoman.startsWith('sh') &&
    hitRoman.startsWith('s') &&
    !hitRoman.startsWith('sh')
  ) {
    return TIER_DICT
  }
  if (source === 'fuzzy' && isAInsertionOnly(typedRoman, hitRoman)) return TIER_DICT
  // Fuzzy with aa-lengthening + inserts (ank→aanak/aanka) must not EXACT-steal.
  if (source === 'fuzzy' && hitRoman && typedRoman && hitRoman.length > typedRoman.length + 1) {
    return TIER_DICT
  }
  // Productive stem expansion never gets hard EXACT (padi: પદિ from pad+i must
  // not outrank soft exact પડી). Evidence-pool DICT only.
  if (source === 'stem_matra' || source === 'stem_postfix' || source === 'stem_inflection' || source === 'stem_compound') {
    return TIER_DICT
  }
  // Near-exact weak suffixes: EXACT only when typed has no lexicon entry.
  if (source === 'near_exact') {
    if (typedRoman && (APPLE_LEXICON.has(typedRoman) || DICT_TRIE.findExact(typedRoman))) {
      return TIER_DICT
    }
    return TIER_EXACT
  }
  if (source === 'fuzzy') return TIER_DICT
  if (source === 'strict') return TIER_EXACT
  return TIER_DICT
}

/** True when hit is typed with a digraph collapsed (sh→s, th→t, …). */
function isDigraphStripFuzzy(typed, hit) {
  if (!typed || !hit || hit.length >= typed.length) return false
  const pairs = [
    ['chh', 'ch'], ['chh', 'c'], ['kh', 'k'], ['gh', 'g'], ['th', 't'], ['dh', 'd'],
    ['ph', 'p'], ['bh', 'b'], ['sh', 's'], ['Sh', 's'], ['Sh', 'sh'], ['jh', 'j'],
  ]
  const t = String(typed).toLowerCase()
  const h = String(hit).toLowerCase()
  for (const [long, short] of pairs) {
    if (!t.includes(long)) continue
    // Rebuild: replace one occurrence of long with short → equals hit
    let idx = 0
    while (idx <= t.length - long.length) {
      const at = t.indexOf(long, idx)
      if (at < 0) break
      if (t.slice(0, at) + short + t.slice(at + long.length) === h) return true
      idx = at + 1
    }
  }
  return false
}

/**
 * Lexicon stem + vowel matra (shabd+o → શબ્દો). Scalable for all vowel signs.
 * Stem must be a lexicon roman key ending in an inherent-a consonant native.
 */
const STEM_MATRA_SUFFIXES = [
  ['aa', '\u0ABE'], // ા
  ['ii', '\u0AC0'], // ી
  ['ee', '\u0AC0'],
  ['uu', '\u0AC2'], // ૂ
  ['oo', '\u0AC2'],
  ['ai', '\u0AC8'], // ૈ
  ['au', '\u0ACC'], // ૌ
  // bare trailing 'a' omitted — peels gharma→gharm / false stems
  ['i', '\u0ABF'], // િ
  ['u', '\u0AC1'], // ુ
  ['e', '\u0AC7'], // ે
  ['o', '\u0ACB'], // ો
]

/** Roman postpositions / morph suffixes → GU (mulya+maa → મૂલ્યમાં). Longest first. */
const STEM_POSTFIX_SUFFIXES = [
  ['maanthi', 'માંથી'],
  ['maan', 'માં'],
  ['maa', 'માં'],
  ['man', 'માં'],
  ['ma', 'માં'], // gharma → ઘરમાં; moolyama → મૂલ્યમાં
  ['valun', 'વાળું'],
  ['vali', 'વાળી'],
  ['vala', 'વાળા'],
  ['valo', 'વાળો'],
  ['thi', 'થી'],
  ['nee', 'ની'],
  ['nii', 'ની'],
  ['noo', 'નું'],
  ['nuu', 'નું'],
  ['naa', 'ના'],
  ['ni', 'ની'],
  ['nu', 'નું'],
  ['na', 'ના'],
  ['no', 'નો'],
  ['ne', 'ને'],
]

function configuredStemPostfixSuffixes() {
  const policy = (RUNTIME && RUNTIME.policy) || {}
  const configured = Array.isArray(policy.stem_postfix_suffixes)
    ? policy.stem_postfix_suffixes
    : STEM_POSTFIX_SUFFIXES
  const experimental = policy.experimental_families &&
    Array.isArray(policy.experimental_families.plural_postpositions)
    ? policy.experimental_families.plural_postpositions
    : []
  return experimental.concat(configured)
}

function lexiconStemMatraHits(typed) {
  const out = []
  const lower = String(typed || '').toLowerCase()
  if (lower.length < 3) return out
  for (const [suf, matra] of STEM_MATRA_SUFFIXES) {
    if (lower.length <= suf.length + 1) continue
    if (!lower.endsWith(suf)) continue
    // Don't peel vowel if preceding char is also a vowel carrier (kyaare≠kyaar+e).
    const stem = lower.slice(0, -suf.length)
    if (!stem || stem.length < 2) continue
    const last = stem[stem.length - 1]
    if ('aeiou'.includes(last)) continue
    const word = APPLE_LEXICON.get(stem) || DICT_TRIE.findExact(stem)
    if (!word) continue
    const w = lexiconWeight(stem)
    if (matra === null) {
      out.push({ roman: stem, word, weight: w, source: 'stem_matra' })
    } else if (endsWithConsonantWithImplicitA(word)) {
      out.push({ roman: stem + suf, word: word + matra, weight: Math.max(w, 100), source: 'stem_matra' })
    }
  }
  return out
}

function lookupLexiconStem(stem) {
  let word = APPLE_LEXICON.get(stem) || DICT_TRIE.findExact(stem)
  let bestRoman = stem
  let w = word ? lexiconWeight(stem) : 0
  if (word) return { word, roman: bestRoman, weight: w }
  // Fuzzy stem (mulya → moolya) without baking per word.
  for (const alt of generateAlternateForms(stem, (RUNTIME && RUNTIME.policy) || {})) {
    const hit = APPLE_LEXICON.get(alt) || DICT_TRIE.findExact(alt)
    if (!hit) continue
    const ww = lexiconWeight(alt)
    if (!word || ww > w) {
      word = hit
      bestRoman = alt
      w = ww
    }
  }
  return word ? { word, roman: bestRoman, weight: w } : null
}

/** Stem + postposition (mulyama → મૂલ્ય + માં). Skips if roman stem ends in a vowel letter. */
function lexiconStemPostfixHits(typed) {
  const out = []
  const seen = new Set()
  const lower = String(typed || '').toLowerCase()
  if (lower.length < 4) return out
  let matchedSuffixLength = null
  const suffixes = configuredStemPostfixSuffixes()
    .filter(([suf]) => suf && lower.endsWith(suf))
    .sort((a, b) => b[0].length - a[0].length)
  for (const [suf, guSuf] of suffixes) {
    if (matchedSuffixLength !== null && suf.length < matchedSuffixLength) break
    if (lower.length <= suf.length + 2) continue
    if (!lower.endsWith(suf)) continue
    const stem = lower.slice(0, -suf.length)
    if (!stem || stem.length < 2) continue
    const hit = lookupLexiconStem(stem)
    if (!hit) continue
    // Short vowel-final stems are ambiguous (mane must not become ma+ne).
    // Longer, strongly attested stems productively take Gujarati postpositions.
    const vowelFinal = /(?:e|i|o|u|aa|ii|ee|uu|oo|ai|au)$/.test(stem)
    const stemValidity = dictionaryValidity(hit.word)
    if (
      vowelFinal &&
      (stem.length < 5 || (hit.weight < LEXICON_STRONG_WEIGHT && !stemValidity.attested))
    ) continue
    if (suf === 'o' && stem.length < 5) continue
    // Prefer bare inherent-a stems; allow nasal/matra stems (હિંમતમાં).
    if (
      !endsWithConsonantWithImplicitA(hit.word) &&
      !/[\u0ABE\u0AC0\u0AC1\u0AC2\u0AC7\u0AC8\u0ACB\u0ACC\u0A82]$/.test(hit.word)
    ) {
      continue
    }
    let composedSuffix = guSuf
    if (endsWithConsonantWithImplicitA(hit.word) && guSuf.startsWith('ઓ')) {
      composedSuffix = 'ો' + guSuf.slice(1)
    }
    const word = hit.word + composedSuffix
    if (seen.has(word)) continue
    seen.add(word)
    out.push({
      roman: hit.roman + suf,
      word,
      weight: Math.max(hit.weight, 120),
      source: 'stem_postfix',
    })
    matchedSuffixLength = suf.length
    if (out.length >= 8) break
  }
  return out
}

/** Productive word-level inflections (future, infinitive, agreement), policy-owned. */
function lexiconStemInflectionHits(typed) {
  const out = []
  const seen = new Set()
  const lower = String(typed || '').toLowerCase()
  const policy = (RUNTIME && RUNTIME.policy) || {}
  const suffixes = Array.isArray(policy.stem_inflection_suffixes)
    ? policy.stem_inflection_suffixes
    : []
  for (const [suffix, nativeSuffix] of suffixes) {
    if (!suffix || !nativeSuffix || lower.length <= suffix.length + 1 || !lower.endsWith(suffix)) continue
    const stem = lower.slice(0, -suffix.length)
    for (const stemQuery of [stem, stem + 'a']) {
      const hit = lookupLexiconStem(stemQuery)
      if (!hit || !hit.word) continue
      const word = hit.word + nativeSuffix
      if (seen.has(word)) continue
      seen.add(word)
      out.push({
        roman: hit.roman + suffix,
        word,
        weight: Math.max(hit.weight, 120),
        source: 'stem_inflection',
      })
    }
    if (out.length >= 8) break
  }
  return out
}

/** Bounded exact-part compound generation; no word identities or free-form splits. */
function lexiconCompoundHits(typed) {
  const lower = String(typed || '').toLowerCase()
  const policy = ((RUNTIME && RUNTIME.policy) || {}).morphology || {}
  const minInput = Math.max(6, Number(policy.compound_min_input_length) || 8)
  const minPart = Math.max(2, Number(policy.compound_min_component_length) || 3)
  const maxComponents = Math.max(2, Math.min(3, Number(policy.max_components) || 3))
  const maxCandidates = Math.max(1, Math.min(16, Number(policy.max_compound_candidates) || 8))
  if (lower.length < minInput) return []

  const partCache = new Map()
  function part(roman) {
    if (partCache.has(roman)) return partCache.get(roman)
    const word = APPLE_LEXICON.get(roman) || DICT_TRIE.findExact(roman)
    if (!word) {
      partCache.set(roman, null)
      return null
    }
    const weight = lexiconWeight(roman)
    const validity = dictionaryValidity(word)
    const value = (weight >= 100 || validity.attested)
      ? { roman, word, weight, evidence: validity.evidence || 0 }
      : null
    partCache.set(roman, value)
    return value
  }

  const out = []
  const seen = new Set()
  function emit(parts) {
    const word = parts.map((item) => item.word).join('')
    if (!word || seen.has(word)) return
    seen.add(word)
    const evidence = parts.reduce((sum, item) => sum + Math.log1p(item.evidence), 0)
    const weight = Math.max(100, Math.min(...parts.map((item) => item.weight || 100)))
    out.push({
      roman: parts.map((item) => item.roman).join(''),
      word,
      weight,
      evidence,
      components: parts.length,
      source: 'stem_compound',
    })
  }

  for (let first = minPart; first <= lower.length - minPart; first += 1) {
    const left = part(lower.slice(0, first))
    if (!left) continue
    const right = part(lower.slice(first))
    if (right) emit([left, right])
    if (maxComponents < 3) continue
    for (let second = first + minPart; second <= lower.length - minPart; second += 1) {
      const middle = part(lower.slice(first, second))
      if (!middle) continue
      const tail = part(lower.slice(second))
      if (tail) emit([left, middle, tail])
    }
  }
  out.sort((a, b) => b.evidence - a.evidence || b.weight - a.weight || a.components - b.components)
  return out.slice(0, maxCandidates)
}

/**
 * All roman strings to try against the Apple lexicon for this input.
 * Scalable fuzzy match — no per-word baking.
 */
function expandRomanQueries(input) {
  const q = new Set()
  const lower = input.toLowerCase()
  q.add(lower)
  q.add(input)
  const policy = (RUNTIME && RUNTIME.policy) || {}
  for (const form of generateAlternateForms(lower, policy)) {
    q.add(form)
    for (const ended of withEndingVariants(form, policy.ending_variants)) q.add(ended)
  }
  // Weighted lattice — policy confusion_pairs + costs (fallback: DEFAULT_CONFUSION_PAIRS)
  try {
    const pairs =
      (policy.confusion_pairs && policy.confusion_pairs.length && policy.confusion_pairs) ||
      DEFAULT_CONFUSION_PAIRS
    const lattice = Object.assign({}, DEFAULT_LATTICE, policy.lattice || {})
    for (const { roman } of expandRomanLattice(lower, pairs, lattice)) {
      q.add(roman)
      if (q.size > 160) break
    }
  } catch (_e) {}
  return q
}

function getEnvBool(env, key, fallback) {
  try {
    if (env && env.engine && env.engine.schema && env.engine.schema.config) {
      const config = env.engine.schema.config
      if (typeof config.get_bool === 'function') {
        return config.get_bool(key) ?? fallback
      }
      if (typeof config.getBool === 'function') {
        return config.getBool(key) ?? fallback
      }
    }
  } catch (e) {
    return fallback
  }
  return fallback
}

function getEnvNumber(env, key, fallback) {
  try {
    if (env && env.engine && env.engine.schema && env.engine.schema.config) {
      const config = env.engine.schema.config
      if (typeof config.get_double === 'function') {
        const value = config.get_double(key)
        return Number.isFinite(value) ? value : fallback
      }
      if (typeof config.getDouble === 'function') {
        const value = config.getDouble(key)
        return Number.isFinite(value) ? value : fallback
      }
    }
  } catch (e) {
    return fallback
  }
  return fallback
}

function getEnvString(env, key, fallback) {
  try {
    const config = env && env.engine && env.engine.schema && env.engine.schema.config
    if (!config) return fallback
    if (typeof config.get_string === 'function') return config.get_string(key) || fallback
    if (typeof config.getString === 'function') return config.getString(key) || fallback
  } catch (_e) {}
  return fallback
}

function learningNativeCount(text) {
  if (!USER_LEARNING || !USER_LEARNING.choices || !text) return 0
  let n = 0
  for (const entry of Object.values(USER_LEARNING.choices)) {
    const meta = entry && entry.natives && entry.natives[text]
    if (meta) n += Number(meta.explicit_count) || 0
  }
  return n
}

function scoreCandidate(text, isPhonetic) {
  const unigramCount = nativeEvidence(text).unigram
  const userCount = learningNativeCount(text)
  const unigramScore = normalizedScore(unigramCount, nativeEvidenceMax()) * LM_WEIGHTS.unigram
  const userScore = userBoost(userCount)
  const phoneticPenalty = isPhonetic ? -0.15 : 0
  return unigramScore + userScore + phoneticPenalty
}

/** Compatibility hook: non-number commits intentionally do not learn. */
export function learnCommittedChoice(env, word, typedRoman) {
  // Compatibility hook used by commit_on_punct_processor. Only the numbered
  // selection tracker is allowed to update preference learning.
  void env
  void word
  void typedRoman
  return false
}

/** Cheap roman distance for soft-gate ranking (prefer closer fuzzy hits). */
function romanCloseness(a, b) {
  if (!a || !b) return 0
  if (a === b) return 100
  const x = String(a).toLowerCase()
  const y = String(b).toLowerCase()
  if (x === y) return 100
  if (y.startsWith(x) || x.startsWith(y)) {
    return 80 - Math.min(40, Math.abs(x.length - y.length) * 8)
  }
  let shared = 0
  const n = Math.min(x.length, y.length)
  for (let i = 0; i < n; i++) {
    if (x[i] === y[i]) shared += 1
    else break
  }
  return Math.max(0, shared * 6 - Math.abs(x.length - y.length) * 4)
}

/** URL / email / host-looking roman → Latin-only (no script suggest). */
function looksLikeLatinLiteral(s) {
  if (!s) return false
  return /@|:\/\/|(^|\.)(com|org|net|edu|io|gov)(\b|$)/i.test(s) || /^https?:\/\//i.test(s)
}

/**
 * Numbers should stay Western/Arabic digits (2.9 → 2.9, not 2.૯ / ૨.૯).
 * Pure digit strings and decimals are Latin-first.
 */
function looksLikeAsciiNumber(s) {
  if (!s) return false
  if (/^\d+\.\d*$/.test(s) || /^\d*\.\d+$/.test(s) || /\d\.\d/.test(s)) return true
  if (/^\d+$/.test(s)) return true
  return false
}

// ---------------------------------------------------------------------------
// Rime Translator
// ---------------------------------------------------------------------------

/**
 * @implements {Translator}
 */
export class GujaratiTranslator {
  constructor(env) {
    console.log('$qjs$ gujarati translator init')
    logRuntimeCapabilities(env)
    initRuntimeStorage(env)
    if (RUNTIME && (RUNTIME.mode === 'trie' || RUNTIME.mode === 'map')) {
      APPLE_EXCEPTIONS = RUNTIME.lexicon.exceptions || new Map()
      console.log('$qjs$ runtime storage mode=' + RUNTIME.mode)
    } else {
      console.error('$qjs$ refusing text loaders in release mode')
    }
    // enable_user_learning is authoritative when present; else fall back to enable_user_lm.
    // Explicit false always wins (never OR with legacy true).
    {
      let learningKeySet = false
      try {
        const config = env && env.engine && env.engine.schema && env.engine.schema.config
        if (config) {
          const raw =
            typeof config.get_bool === 'function'
              ? config.get_bool('translator/enable_user_learning')
              : typeof config.getBool === 'function'
                ? config.getBool('translator/enable_user_learning')
                : null
          if (raw === true || raw === false) {
            USER_LEARNING_ENABLED = raw
            learningKeySet = true
          }
        }
      } catch (_e) {}
      if (!learningKeySet) {
        USER_LEARNING_ENABLED = getEnvBool(env, 'translator/enable_user_lm', true)
      }
    }
    USER_LEARNING_THRESHOLD = Math.max(
      EXPLICIT_PROMOTION_THRESHOLD,
      Math.floor(getEnvNumber(env, 'translator/user_learning_threshold', EXPLICIT_PROMOTION_THRESHOLD))
    )
    if (USER_LEARNING_ENABLED) {
      USER_LEARNING = initLearningSession(env)
    }
    this.neuralMode = getEnvString(env, 'translator/neural_mode', 'auto')
    this.requiredNeuralMissing =
      this.neuralMode === 'required' && !neuralCapability(env).available
    if (this.requiredNeuralMissing) {
      console.error('$qjs$ deployment error: neural_mode=required but Gujarati model is unavailable')
    }
    this.menuCache = new Map()
  }

  finalizer() {
    console.log('$qjs$ gujarati translator finit')
  }

  /**
   * @param {string} input
   * @param {Segment} segment
   * @param {Environment} env
   * @returns {Array<Candidate>}
   */
  translate(input, segment, env) {
    try {
      if (!input || input.length === 0) {
        return []
      }
      if (this.requiredNeuralMissing) return []

      if (looksLikeLatinLiteral(input) || looksLikeAsciiNumber(input)) {
        const cand = new Candidate('latin', segment.start, segment.end, input, '', 100)
        cand.quality = 100
        return [cand]
      }

      if (!RUNTIME) initRuntimeStorage(env)

      const enableUserLm = USER_LEARNING_ENABLED
      if (enableUserLm) USER_LEARNING = getLearningSession(env)
      USER_LEARNING_THRESHOLD = Math.max(
        1,
        Math.floor(getEnvNumber(env, 'translator/user_learning_threshold', USER_LEARNING_THRESHOLD))
      )
      // No per-keystroke user-file I/O — learning loaded once at init / updated on commit.
      const hardGate = getEnvBool(env, 'translator/lexicon_hard_gate', true)
      const fuzzyExactSoft = getEnvBool(env, 'translator/fuzzy_exact_soft', true)
      const includeLatin = getEnvBool(env, 'translator/include_latin', true)
      const emojiEnable = getEnvBool(env, 'translator/emoji_enable', true)
      const maxPrefix = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_prefix', 3)))
      const maxPhonetic = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_phonetic', 4)))
      const maxEmoji = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_emoji', 2)))
      const maxCandidates = Math.max(1, Math.floor(getEnvNumber(env, 'translator/max_candidates', 6)))
      const neuralMode = getEnvString(env, 'translator/neural_mode', 'auto')
      const maxNeural = Math.max(1, Math.min(8, Math.floor(
        getEnvNumber(env, 'translator/max_neural_candidates', 4)
      )))
      LM_WEIGHTS.unigram = getEnvNumber(env, 'translator/lm_unigram_weight', LM_WEIGHTS.unigram)
      LM_WEIGHTS.user = getEnvNumber(env, 'translator/lm_user_weight', LM_WEIGHTS.user)
      const lower = input.toLowerCase()
      const learningEntry = enableUserLm && USER_LEARNING && USER_LEARNING.choices
        ? USER_LEARNING.choices[lower]
        : null
      const cacheKey = [
        input, hardGate, fuzzyExactSoft, includeLatin, emojiEnable, maxPrefix,
        maxPhonetic, maxEmoji, maxCandidates, neuralMode, maxNeural,
        JSON.stringify(learningEntry || null),
      ].join('\u001f')
      const materialize = (descriptors) => descriptors.map((item) => {
        const candidate = new Candidate(
          item.candidateType,
          segment.start,
          segment.end,
          item.native,
          item.comment,
          0
        )
        candidate.quality = item.quality
        if (item.debugRank) candidate.debugRank = item.debugRank
        return candidate
      })
      const cached = this.menuCache.get(cacheKey)
      if (cached) return materialize(cached)
      const seen = new Set()
      const items = []

      function pushCand(text, comment, quality, tier, isPhonetic, romanKey, exactSource, meta) {
        if (!text) return false
        text = normalizeGujaratiOrthography(text)
        const metaNeuralLogProb = Number(meta && meta.neuralLogProb)
        const metaNeuralRelativeLogProb = Number(meta && meta.neuralRelativeLogProb)
        const hasNeuralEvidence =
          Number.isFinite(metaNeuralLogProb) && Number.isFinite(metaNeuralRelativeLogProb)
        if (seen.has(text)) {
          // Upgrade tier if a stronger source rediscovers the same native form.
          for (let i = 0; i < items.length; i++) {
            const it = items[i]
            if (it.native !== text) continue
            const provenance = exactSource || (tier === TIER_EMOJI ? 'emoji' : isPhonetic ? 'phonetic' : 'unknown')
            if (!it.provenance.includes(provenance)) it.provenance.push(provenance)
            if (hasNeuralEvidence) {
              it.neuralSeen = true
              it.neuralRawLogProb = Math.max(it.neuralRawLogProb, metaNeuralLogProb)
              it.neuralRelativeLogProb = Math.max(
                it.neuralRelativeLogProb,
                metaNeuralRelativeLogProb
              )
              it.neuralLogProb = it.neuralRelativeLogProb
            }
            if (tier < it.tier) {
              it.tier = tier
              it.exactSource = exactSource || it.exactSource
              it.romanKey = romanKey || it.romanKey
              it.weight = Math.max(it.weight || 0, tier === TIER_EMOJI ? quality : lexiconWeight(romanKey || lower))
              it.closeness = Math.max(it.closeness || 0, romanCloseness(lower, romanKey || lower))
              it.comment = comment || it.comment
              return true
            }
            return false
          }
          return false
        }
        seen.add(text)
        const source = exactSource || (tier === TIER_EMOJI ? 'emoji' : tier === TIER_LATIN ? 'latin' : isPhonetic ? 'phonetic' : 'lexicon')
        items.push(makeCandidateRecord({
          native: text,
          text,
          typedRoman: lower,
          queryRoman: romanKey || lower,
          comment: comment || '',
          candidateType: tier === TIER_EMOJI ? 'emoji' : tier === TIER_LATIN ? 'latin' : 'gujarati',
          source,
          provenance: [source],
          transformFamily: (meta && meta.transformFamily) || (source === 'strict' ? 'typed' : source),
          transformCost: Math.max(0, Number(meta && meta.transformCost) || 0),
          neuralLogProb: hasNeuralEvidence ? metaNeuralRelativeLogProb : 0,
          neuralRawLogProb: hasNeuralEvidence ? metaNeuralLogProb : -Infinity,
          neuralRelativeLogProb: hasNeuralEvidence ? metaNeuralRelativeLogProb : -Infinity,
          neuralSeen: hasNeuralEvidence,
          emojiConfidence: Math.max(0, Math.min(1, Number(meta && meta.emojiConfidence) || 0)),
          displayGroup: tier === TIER_EMOJI ? 'emoji' : tier === TIER_LATIN ? 'latin' : 'gu',
          tier,
          isPhonetic: !!isPhonetic,
          romanKey: romanKey || lower,
          weight: Number.isFinite(Number(meta && meta.weight))
            ? Number(meta.weight)
            : (tier === TIER_EMOJI ? quality : lexiconWeight(romanKey || lower)),
          exactSource: exactSource || null,
          closeness: romanCloseness(lower, romanKey || lower),
        }))
        return true
      }

      // GENERAL fuzzy lexicon lookup: expand roman confusions/endings, then hit 96k Apple dict.
      // poshatu → poshatun → પોષતું; ketli → keTlii → (phonetic) કેટલી + unigram boost.
      const romanQueries = expandRomanQueries(input)
      const runtimePolicy = (RUNTIME && RUNTIME.policy) || {}
      const altForms = generateAlternateForms(lower, runtimePolicy)
      const latticeCosts = new Map([[lower, 0]])
      try {
        for (const form of expandRomanLattice(
          lower,
          runtimePolicy.confusion_pairs || DEFAULT_CONFUSION_PAIRS,
          Object.assign({}, DEFAULT_LATTICE, runtimePolicy.lattice || {})
        )) {
          latticeCosts.set(form.roman, Number(form.cost) || 0)
        }
      } catch (_e) {}

      const exc = APPLE_EXCEPTIONS.get(lower) || APPLE_EXCEPTIONS.get(input)
      if (exc) {
        pushCand(exc, input, 999, TIER_EXACT, false, lower, 'strict')
      }

      const exactHits = []
      const generatedRomanKeys = new Set()
      // The public pure generator is the authoritative lattice/Trie entry.
      // The adapter supplements it only with non-lattice legacy alternate forms.
      for (const record of modGenerateCandidates(lower, RUNTIME, runtimePolicy)) {
        generatedRomanKeys.add(record.queryRoman || record.romanKey)
        exactHits.push({
          roman: record.queryRoman || record.romanKey,
          word: record.native,
          weight: record.weight,
          source: record.source,
          transformCost: record.transformCost,
        })
      }
      for (const q of romanQueries) {
        if (generatedRomanKeys.has(q)) continue
        const word = APPLE_LEXICON.get(q) || DICT_TRIE.findExact(q)
        if (!word) continue
        const source = q === lower || q === input ? 'strict' : 'fuzzy'
        exactHits.push({
          roman: q,
          word,
          weight: Math.max(lexiconWeight(q), q === lower ? 1 : 0),
          source,
          transformCost: source === 'strict' ? 0 : (latticeCosts.get(q) ?? 2),
        })
      }
      exactHits.sort((a, b) => {
        // Prefer typed exact over fuzzy so a→aa soft keys cannot hide strict (kyare).
        const as = a.source === 'strict' ? 0 : 1
        const bs = b.source === 'strict' ? 0 : 1
        if (as !== bs) return as - bs
        return b.weight - a.weight || a.roman.length - b.roman.length
      })
      const typedForTier = input.length === 1 ? input : lower
      for (const hit of exactHits) {
        const q = hit.roman === lower ? 950 : 880
        const tier = lexiconHitTier(hit.source, hit.weight, typedForTier, hit.roman)
        pushCand(
          hit.word,
          hit.roman === lower ? input : hit.roman,
          q + Math.min(40, Math.log1p(hit.weight) * 5),
          tier,
          false,
          hit.roman,
          hit.source,
          { transformFamily: hit.source === 'strict' ? 'typed' : 'fuzzy', transformCost: hit.transformCost }
        )
      }

      // Lexicon stem + vowel matra (shabd+o → શબ્દો) for all vowel signs.
      for (const hit of lexiconStemMatraHits(lower)) {
        const tier = lexiconHitTier('stem_matra', hit.weight, typedForTier, hit.roman)
        pushCand(hit.word, input, 920 + Math.min(40, Math.log1p(hit.weight) * 5), tier, false, hit.roman, 'stem_matra')
      }
      // Lexicon stem + postposition (mulyamaa → મૂલ્યમાં).
      for (const hit of lexiconStemPostfixHits(lower)) {
        const tier = lexiconHitTier('stem_postfix', hit.weight, typedForTier, hit.roman)
        pushCand(hit.word, input, 930 + Math.min(40, Math.log1p(hit.weight) * 5), tier, false, hit.roman, 'stem_postfix')
      }
      for (const hit of lexiconStemInflectionHits(lower)) {
        const tier = lexiconHitTier('stem_inflection', hit.weight, typedForTier, hit.roman)
        pushCand(
          hit.word,
          input,
          925 + Math.min(40, Math.log1p(hit.weight) * 5),
          tier,
          false,
          hit.roman,
          'stem_inflection',
          { transformFamily: 'stem_inflection', transformCost: 1, weight: hit.weight }
        )
      }
      for (const hit of lexiconCompoundHits(lower)) {
        pushCand(
          hit.word,
          input,
          920 + Math.min(35, hit.evidence),
          TIER_DICT,
          false,
          hit.roman,
          'stem_compound',
          {
            transformFamily: 'stem_compound',
            transformCost: Math.max(1, hit.components - 1),
            weight: hit.weight,
          }
        )
      }

      // Near-exact lexicon: typed + weak suffix (poshatu→poshatun).
      // Only from the typed roman (not a→aa expansions: ank↛aankh), and only when
      // typed has no lexicon entry — otherwise ghar+m/gnan+m steal EXACT over घર/જ્ઞાન.
      const typedInLex =
        APPLE_LEXICON.has(lower) ||
        APPLE_LEXICON.has(input) ||
        !!DICT_TRIE.findExact(lower) ||
        !!DICT_TRIE.findExact(input)
      if (!typedInLex) {
        for (const seed of [lower, input]) {
          if (!seed || seed.length < 2) continue
          for (const entry of DICT_TRIE.findPrefixEntries(seed, 12)) {
            if (!entry || !entry.value) continue
            if (!entry.key.startsWith(seed)) continue
            const suf = entry.key.slice(seed.length)
            if (!isNearExactRomanSuffix(suf, entry.key, seed.length)) continue
            const w = lexiconWeight(entry.key)
            const tier = lexiconHitTier('near_exact', w, typedForTier, entry.key)
            pushCand(
              entry.value,
              input,
              900 + Math.min(50, Math.log1p(w) * 6),
              tier,
              false,
              entry.key,
              'near_exact',
              { transformFamily: 'near_exact', transformCost: Math.max(1.5, suf.length * 1.5), weight: w }
            )
          }
        }
      }

      const exactItems = items.filter((x) => x.tier === TIER_EXACT)
      const exactCount = exactItems.length
      const hasStrictExact = exactItems.some((x) => x.exactSource === 'strict')
      // Weak fuzzy EXACT only (rare after soft demotion): still allow attested phonetics.
      const softExactOnly =
        fuzzyExactSoft &&
        exactCount > 0 &&
        !hasStrictExact &&
        exactItems.every((x) => (x.weight || 0) < LEXICON_STRONG_WEIGHT)

      // Latin only after we know exact/dict tiers will sort above it
      if (includeLatin) {
        pushCand(input, '', 400, TIER_LATIN, false, lower, null)
      }

      // Generate phonetics, then RESCORE with native wordlist/stems/spell-dicts.
      // Indic IME grammar: schwa-default + productive conjuncts + nasal final -u.
      const phoneticForms = []
      const seenPhon = new Set()
      function addPhon(g) {
        if (!g || g === input || g === lower || seen.has(g)) return
        if (seenPhon.has(g)) return
        seenPhon.add(g)
        phoneticForms.push(g)
      }
      for (const g of phoneticFormsForRoman(input, runtimePolicy)) addPhon(g)
      // IAST place twin for bare consonants (n↔N → ન and ણ both in menu).
      if (input.length === 1 && IAST_PLACE_PAIR[input]) {
        for (const g of phoneticFormsForRoman(IAST_PLACE_PAIR[input], runtimePolicy)) addPhon(g)
      } else if (lower.length === 1 && IAST_PLACE_PAIR[lower]) {
        for (const g of phoneticFormsForRoman(IAST_PLACE_PAIR[lower], runtimePolicy)) addPhon(g)
      }
      for (const form of altForms) {
        if (form.toLowerCase() === lower) continue
        for (const g of phoneticFormsForRoman(form, runtimePolicy)) addPhon(g)
      }

      const phonScored = []
      for (const text of phoneticForms) {
        if (seen.has(text)) continue
        const validity = dictionaryValidity(text)
        const known = KNOWN_WORDS.has(text) || validity.present
        // Hard-gate: drop invented phonetics when lexicon EXACT exists; still keep
        // attested / spell-dict forms (n→ણ exact must not hide dental ન).
        // Soft-fill / a-insertion hits are TIER_DICT (not EXACT), so exactCount stays 0 and
        // high-frequency phonetics can outrank them (mne → મને over soft mane→માને).
        if (hardGate && exactCount > 0 && !known) {
          if (hasStrictExact || softExactOnly) {
            if (!validity.attested && !validity.spellOk) continue
          } else {
            continue
          }
        }
        phonScored.push({ text, known, validity })
      }
      phonScored.sort((a, b) => {
        // Direct unigram hit beats stem-only / floor-attested phonetic cousins.
        const uniA = a.validity.unigram || 0
        const uniB = b.validity.unigram || 0
        if ((uniA > 0) !== (uniB > 0)) return uniA > 0 ? -1 : 1
        if (a.validity.spellOk !== b.validity.spellOk) return a.validity.spellOk ? -1 : 1
        if (a.validity.attested !== b.validity.attested) return a.validity.attested ? -1 : 1
        if (uniB !== uniA) return uniB - uniA
        if (b.validity.score !== a.validity.score) return b.validity.score - a.validity.score
        return 0
      })

      let phoneticCap = maxPhonetic
      const hasStrongExact = exactItems.some(
        (x) => (x.weight || 0) >= LEXICON_STRONG_WEIGHT && x.exactSource === 'strict'
      )
      if (hasStrongExact) phoneticCap = Math.min(phoneticCap, 2)

      let phoneticAdded = 0
      let uniBackedPhon = 0
      const attestedFloor = nativeEvidenceFloor()
      for (const item of phonScored) {
        if (phoneticAdded >= phoneticCap) break
        const uniHit = item.validity.unigram || 0
        // Once we have uni-backed DICT phonetics, skip stem-only floor cousins.
        if (uniBackedPhon >= 2 && uniHit <= attestedFloor && !item.validity.uniStrong) {
          continue
        }
        const tier = item.validity.attested ? TIER_DICT : TIER_PHONETIC
        const q = item.validity.attested
          ? 700 + Math.min(99, item.validity.score * 12)
          : (item.known ? 300 : 200)
        if (pushCand(item.text, input, q, tier, true, lower, null)) {
          phoneticAdded += 1
          if (item.validity.uniStrong || uniHit > attestedFloor) uniBackedPhon += 1
        }
      }

      if (exactCount === 0 && phoneticAdded === 0) {
        const fallback = phoneticFormsForRoman(input, runtimePolicy)[0]
        if (fallback && fallback !== input) {
          const v = dictionaryValidity(fallback)
          pushCand(fallback, input, v.attested ? 720 : 250, v.attested ? TIER_DICT : TIER_PHONETIC, true, lower, null)
        }
      }

      {
        const neural = neuralNBest(env, lower, maxNeural, neuralMode)
        if (neural.requiredMissing) {
          console.error('$qjs$ neural_mode=required but Gujarati model bridge is unavailable')
        } else if (neural.error) {
          console.error('$qjs$ neural inference failed: ' + neural.error)
        }
        const bestNeuralLogProb = neural.candidates.length
          ? Math.max(...neural.candidates.map((item) => item.logProb))
          : 0
        for (const result of neural.candidates) {
          const validity = dictionaryValidity(result.native)
          pushCand(
            result.native,
            'model',
            650,
            validity.attested ? TIER_DICT : TIER_PHONETIC,
            false,
            lower,
            'neural',
            {
              transformFamily: 'neural',
              transformCost: 0,
              neuralLogProb: result.logProb,
              neuralRelativeLogProb: result.logProb - bestNeuralLogProb,
              weight: validity.evidence || 0,
            }
          )
        }
      }

      if (input.length >= 2 && maxPrefix > 0) {
        const prefixSeeds = new Set([lower])
        for (const q of romanQueries) {
          if (q.length >= 2) prefixSeeds.add(q)
        }
        const prefixEntries = []
        for (const seed of prefixSeeds) {
          for (const entry of DICT_TRIE.findPrefixEntries(seed, Math.max(maxPrefix * 3, 16))) {
            prefixEntries.push(entry)
          }
        }
        prefixEntries.sort((a, b) => lexiconWeight(b.key) - lexiconWeight(a.key))
        let prefixAdded = 0
        for (const entry of prefixEntries) {
          if (prefixAdded >= maxPrefix) break
          if (!entry || !entry.value) continue
          if (seen.has(entry.value)) continue
          let suffix = ''
          if (entry.key.startsWith(lower)) suffix = entry.key.slice(lower.length)
          else {
            suffix = entry.key.length > lower.length ? entry.key.slice(lower.length) : ''
          }
          const w = lexiconWeight(entry.key)
          if (entry.key.startsWith(lower) && !typedInLex && isNearExactRomanSuffix(suffix, entry.key, lower.length)) {
            const tier = lexiconHitTier('near_exact', w, lower, entry.key)
            if (pushCand(
              entry.value,
              input,
              860 + Math.min(40, Math.log1p(w) * 5),
              tier,
              false,
              entry.key,
              'near_exact',
              { transformFamily: 'near_exact', transformCost: Math.max(1.5, suffix.length * 1.5), weight: w }
            )) {
              prefixAdded += 1
            }
            continue
          }
          if (entry.key === lower) continue
          const comment = suffix ? ('~' + suffix) : input
          if (pushCand(entry.value, comment, 80 + Math.min(40, Math.log1p(w) * 5), TIER_PREFIX, false, entry.key, null)) {
            prefixAdded += 1
          }
        }
      }

      // Emoji suggestions from English / Gujarati-roman keywords (never beat script tiers).
      const emojiByRoman = (RUNTIME && RUNTIME.emoji && RUNTIME.emoji.byRoman) || new Map()
      const emojiByNative = (RUNTIME && RUNTIME.emoji && RUNTIME.emoji.byNative) || new Map()
      if (emojiEnable && maxEmoji > 0 && emojiByRoman.size > 0) {
        const emojiHits = []
        const seenEmoji = new Set()
        function queueEmoji(list, via) {
          if (!list) return
          for (const it of list) {
            if (!it || !it.e || seenEmoji.has(it.e) || seen.has(it.e)) continue
            seenEmoji.add(it.e)
            emojiHits.push({
              emoji: it.e,
              weight: it.w || 100,
              confidence: Number(it.confidence) || 0,
              source: it.source || 'legacy',
              via,
            })
          }
        }
        queueEmoji(emojiByRoman.get(lower), lower)
        // Native forms already in the menu (e.g. પ્રેમ from prem)
        for (const item of items) {
          if (item.tier === TIER_EMOJI) continue
          queueEmoji(emojiByNative.get(item.native), item.native)
        }
        emojiHits.sort((a, b) => b.confidence - a.confidence || b.weight - a.weight)
        let emojiAdded = 0
        for (const hit of emojiHits) {
          if (emojiAdded >= maxEmoji) break
          if (pushCand(
            hit.emoji,
            'emoji',
            50 + Math.min(40, Math.log1p(hit.weight) * 4),
            TIER_EMOJI,
            false,
            lower,
            null,
            { transformFamily: 'emoji_exact', emojiConfidence: hit.confidence }
          )) {
            emojiAdded += 1
          }
        }
      }

      if (items.length === 0) return []

      const scored = items.map((item, index) => {
        const text = item.native || ''
        const lm = item.tier === TIER_EMOJI
          ? Math.log1p(item.weight || 0) * 0.2
          : scoreCandidate(text, item.isPhonetic)
        const freq = Math.log1p(item.weight || 0) * 0.35
        const validity = item.tier === TIER_EMOJI
          ? { score: 0, attested: false, evidence: 0, spellOk: false }
          : dictionaryValidity(text)
        const dictBoost = validity.attested ? validity.score * 1.4 : 0
        const spellBoost = validity.spellOk ? 0.35 : 0
        const closeBoost = (item.closeness || 0) * 0.01
        const unigramCount = nativeEvidence(text).unigram
        const uniBoost = Math.log1p(unigramCount) * 0.55
        const transformPenalty = (Number(item.transformCost) || 0) *
          Number((runtimePolicy.weights && runtimePolicy.weights.transform_cost) || 1.35)
        const neuralBoost = (Number.isFinite(item.neuralRelativeLogProb)
          ? item.neuralRelativeLogProb
          : 0) *
          Number((runtimePolicy.weights && runtimePolicy.weights.neural_log_probability) || 0.35)
        const neuralSourceBoost = item.exactSource === 'neural'
          ? Number((runtimePolicy.weights && runtimePolicy.weights.neural_source_boost) || 0)
          : 0
        let score = lm + freq + dictBoost + spellBoost + closeBoost + uniBoost + neuralBoost + neuralSourceBoost - transformPenalty
        let tier = item.tier
        const isLex =
          item.exactSource === 'strict' ||
          item.exactSource === 'fuzzy' ||
          item.exactSource === 'near_exact' ||
          item.exactSource === 'stem_matra' ||
          item.exactSource === 'stem_postfix' ||
          item.exactSource === 'stem_inflection' ||
          item.exactSource === 'stem_compound'
        if (isLex && (item.weight || 0) > 0 && (item.weight || 0) < LEXICON_STRONG_WEIGHT && unigramCount < 150) {
          score -= freq * 0.85 + 2.8
        }
        // Soft typed lexicon only when a digraph-strip fuzzy competes (vinash vs vinas).
        const typedLex = APPLE_LEXICON.get(lower) || APPLE_EXCEPTIONS.get(lower) || DICT_TRIE.findExact(lower)
        const typedW = lexiconWeight(lower)
        // A strong typed lexicon entry is the ranking contract's first tier.
        // Fuzzy rediscovery may enrich the menu, but cannot share EXACT and
        // steal top-1 merely through native-frequency evidence.
        if (
          item.exactSource === 'fuzzy' &&
          typedLex &&
          typedW >= LEXICON_STRONG_WEIGHT &&
          text !== normalizeGujaratiOrthography(typedLex) &&
          !isInternalVowelLengthExpansion(lower, item.romanKey)
        ) {
          tier = TIER_DICT
        }
        if (typedLex === text && typedW > 0 && typedW < LEXICON_STRONG_WEIGHT) {
          let hasStrip = false
          for (const it of items) {
            if (it.romanKey && isDigraphStripFuzzy(lower, it.romanKey)) {
              hasStrip = true
              break
            }
          }
          if (hasStrip) score += 3.2
        }
        // Prefer Apple bare stems over morph extensions (aachar→આચાર vs આચારાંગ).
        // Do not boost soft typed keys (swagat) or bare IAST letters (n→ણ).
        const bareIast = input.length === 1 && IAST_PLACE_PAIR[input]
        if (typedLex && typedW >= LEXICON_STRONG_WEIGHT && !bareIast) {
          let competingMorph = false
          for (const it of items) {
            if (isNativeMorphExtension(typedLex, it.native)) {
              competingMorph = true
              break
            }
          }
          if (text === typedLex && competingMorph) {
            score += 6.5
          } else if (isNativeMorphExtension(typedLex, text)) {
            score -= 8.5
            if (tier === TIER_EXACT) tier = TIER_DICT
          }
        }
        // Near-exact nasal morph (aad→aadun→આડું) loses to bare typed stem when present.
        if (
          item.exactSource === 'near_exact' &&
          typedLex &&
          typedW >= LEXICON_STRONG_WEIGHT &&
          text !== typedLex &&
          item.romanKey &&
          item.romanKey.length > lower.length
        ) {
          score -= 7.0
          if (tier === TIER_EXACT) tier = TIER_DICT
        }
        // Closeness: prefer lexicon romans equal to typed over longer fuzzy keys.
        if (isLex && item.romanKey === lower && typedW >= LEXICON_STRONG_WEIGHT) score += 2.0
        else if (isLex && item.romanKey && item.romanKey.length > lower.length + 1) score -= 1.5
        // Personalization: preferred_native (3× numbered) → tier above Exact.
        // Explicit count ties break only; never promote before preferred_native.
        if (enableUserLm) {
          const pref = preferredNative(USER_LEARNING, lower)
          if (pref && pref === text) {
            tier = TIER_PERSONALIZED
            score += userRomanBoost(lower, text, USER_LEARNING_THRESHOLD)
          } else {
            const uc = explicitCount(USER_LEARNING, lower, text)
            if (uc > 0) score += userRomanBoost(lower, text, USER_LEARNING_THRESHOLD)
          }
        }
        if (text.includes('ય') && !lower.includes('y')) score -= 4.0
        // A one-letter vowel must represent itself. Fuzzy length expansion may
        // remain as an alternative, but must not outrank the direct phonetic.
        if (
          input.length === 1 &&
          isIndependentVowelToken(input) &&
          item.romanKey !== lower
        ) {
          score -= 30.0
        }
        // IAST case for bare place-contrast letters: n→ન over ણ, N→ણ over ન (same for t/d/l).
        if (input.length === 1 && IAST_PLACE_PAIR[input]) {
          const dental = { n: 'ન', t: 'ત', d: 'દ', l: 'લ', N: 'ણ', T: 'ટ', D: 'ડ', L: 'ળ' }
          const prefer = dental[input]
          const twin = dental[IAST_PLACE_PAIR[input]]
          if (prefer && text === prefer) score += 2.5
          else if (twin && text === twin) score -= 0.35
        }
        if (lower.includes('d') && !/(^|[^a-z])D/.test(lower)) {
          if (text.includes('ડ') && !text.includes('દ')) score -= 1.2
          if (text.includes('દ')) score += 0.5
        }
        if (lower.startsWith('sh')) {
          if (text.startsWith('શ')) score += 3.0
          else if (text.startsWith('સ')) score -= 3.0 + uniBoost * 0.5
        } else if (!lower.includes('sh') && lower.includes('s')) {
          if (text.includes('શ') && !text.includes('ષ')) score -= 0.55
          if (text.includes('સ') && !text.includes('શ')) score += 0.15
        }
        if (lower.includes('z') && !lower.includes('j')) {
          if (text.startsWith('ઝ')) score += 0.5
          else if (text.startsWith('જ')) score -= 0.35
        }
        if (/(mm|nn|tt|kk|ll)/.test(lower)) {
          if (text.includes('\u0ACD')) score += 5.5
          if (text.includes(ANUSVARA) && !text.includes('\u0ACD')) {
            score -= 6.5 + uniBoost * 1.15
            if (tier === TIER_EXACT) tier = TIER_DICT
          }
        } else if (text.includes(ANUSVARA) && /n[kgcjtdTDpb]/.test(lower)) {
          score += 0.35
        }
        if (lower.startsWith('aa')) {
          // Typed aa… → prefer આ over soft/fuzzy અ… (aadas→આડસ not અડાસ).
          if (text.startsWith('આ')) score += 3.5
          else if (text.startsWith('અ')) {
            score -= 4.0
            if (tier === TIER_EXACT) tier = TIER_DICT
          }
        } else if (
          /^(?:[kgcjtdTDpbnmylrsvwxyz]|ch|kh|gh|jh|th|dh|ph|bh|sh|Sh|tr|dr)a(?!a)/i.test(lower)
        ) {
          // Short-a onset + another later `a`: demote native that ONLY long-a's the
          // onset (પારખવ્યું) — not words that also lengthen later (બાંદા / નાહ્યા).
          const leadLong =
            text.startsWith('આ') || /^[\u0A95-\u0AB9]\u0ABE/.test(text)
          if (leadLong) {
            const rest = text.startsWith('આ') ? text.slice(1) : text.slice(2)
            if (!rest.includes('ા') && /a(?!a)/.test(lower.slice(2))) {
              score -= 3.8
            }
          }
        }
        const aVowels = (lower.match(/a+/g) || []).length
        let aa = 0
        for (const ch of text) if (ch === 'ા') aa += 1
        let effectiveAa = aa
        if (text.endsWith('ા') && !lower.endsWith('a') && !lower.endsWith('aa')) {
          effectiveAa = Math.max(0, effectiveAa - 1)
          score -= 1.6
        }
        if (aVowels >= 1 && lower.slice(1).includes('a')) {
          score += 0.2 * effectiveAa
          if (aVowels >= 2 && effectiveAa >= 2) score += 2.5
          else if (aVowels >= 2 && effectiveAa < 2) score -= 1.2
        }
        // Soft corpora often omit a doubled roman vowel while the native form
        // carries a long matra (swagat→swaagat). Prefer a one-step length
        // expansion when it yields stronger orthographic vowel evidence.
        if (
          item.romanKey &&
          item.romanKey !== lower &&
          isInternalVowelLengthExpansion(lower, item.romanKey) &&
          text.includes('ા')
        ) {
          score += 5.25
        }
        if (text.length < lower.length * 0.7) score -= 2.0
        if (!Number.isFinite(score)) {
          console.error('$qjs$ non-finite score native=' + text + ' roman=' + lower)
          score = -1000000
        }
        return {
          ...item,
          score,
          validity,
          index,
          tier,
          uni: validity.unigram || 0,
          stem: validity.stem || 0,
          attested: !!validity.attested,
          userCount: explicitCount(USER_LEARNING, lower, text),
        }
      })

      // A strong Trie entry is a prior, not an unconditional truth. Override it
      // only when the model explicitly scores both forms, strongly prefers a
      // zero-cost typed phonetic form, and the Trie form is not zero-cost.
      const neuralOverrideMargin = Number(
        (runtimePolicy.weights && runtimePolicy.weights.neural_exact_override_margin) || 3.0
      )
      const neuralOverrideMinLength = Math.max(1, Number(
        (runtimePolicy.weights && runtimePolicy.weights.neural_exact_override_min_length) || 2
      ))
      if (lower.length >= neuralOverrideMinLength) {
        const directTypedForms = new Set(phoneticFormsForRoman(lower, runtimePolicy))
        const neuralRanked = scored
          .filter((item) => item.neuralSeen && Number.isFinite(item.neuralRelativeLogProb))
          .sort((a, b) => b.neuralRelativeLogProb - a.neuralRelativeLogProb)
        const bestNeural = neuralRanked[0]
        const strictExact = scored.find(
          (item) => item.tier === TIER_EXACT && item.exactSource === 'strict'
        )
        const bestDirectNeural = neuralRanked.find((item) => directTypedForms.has(item.native))
        const finalSFidelityGap = Number(
          (runtimePolicy.weights && runtimePolicy.weights.neural_final_s_fidelity_gap) || 1.0
        )
        const finalSFidelity = Boolean(
          strictExact && bestDirectNeural && lower.endsWith('s') && !lower.endsWith('sh') &&
          strictExact.native.endsWith('શ') && bestDirectNeural.native.endsWith('સ') &&
          bestDirectNeural.neuralRelativeLogProb >= -finalSFidelityGap
        )
        const strongModelOverride = Boolean(
          bestNeural && strictExact && strictExact.neuralSeen &&
          bestNeural.native !== strictExact.native &&
          directTypedForms.has(bestNeural.native) && !directTypedForms.has(strictExact.native) &&
          bestNeural.neuralRelativeLogProb - strictExact.neuralRelativeLogProb >= neuralOverrideMargin
        )
        const overrideWinner = finalSFidelity ? bestDirectNeural : (strongModelOverride ? bestNeural : null)
        if (strictExact && overrideWinner && overrideWinner.native !== strictExact.native) {
          strictExact.tier = TIER_DICT
          strictExact.score -= neuralOverrideMargin
          overrideWinner.tier = TIER_EXACT
          overrideWinner.score += neuralOverrideMargin
          overrideWinner.provenance = Array.from(new Set([
            ...(overrideWinner.provenance || []),
            'neural_arbitration',
          ]))
        }
      }

      // Soft typed exact beats stem_matra only (padi → પડી > પદિ). Never over
      // productive stem_postfix (gharma / mulyama keep માં forms).
      const hasStemMatra = scored.some((x) => x.exactSource === 'stem_matra')
      const hasStemPostfix = scored.some((x) => x.exactSource === 'stem_postfix')
      const typedW = lexiconWeight(lower)
      for (const item of scored) {
        if (
          item.romanKey === lower &&
          typedW > 0 &&
          typedW < LEXICON_STRONG_WEIGHT &&
          (item.exactSource === 'strict' || item.exactSource === 'fuzzy') &&
          item.tier === TIER_DICT &&
          !item.isPhonetic &&
          /[aeiou]$/.test(lower) &&
          hasStemMatra &&
          !hasStemPostfix
        ) {
          item.score += 5.5
        }
        if (item.exactSource === 'stem_matra' && typedW > 0 && typedW < LEXICON_STRONG_WEIGHT) {
          item.score -= 2.0
        }
        if (item.exactSource === 'stem_postfix' && (item.weight || 0) >= LEXICON_STRONG_WEIGHT) {
          item.score += 4.5
        }
        if (item.exactSource === 'stem_inflection' && (item.weight || 0) >= LEXICON_STRONG_WEIGHT) {
          item.score += 4.5
        }
      }

      // A typed lexicon key remains exact unless a low-cost vowel-length
      // expansion has substantially stronger language evidence. This keeps
      // fuzzy candidates out of EXACT while allowing શાંતિ to beat શાન્તિ.
      const evidenceWinner = scored
        .filter((item) =>
          item.exactSource === 'fuzzy' &&
          (item.transformCost || 0) <= 4 &&
          item.validity && item.validity.attested &&
          isInternalVowelLengthExpansion(lower, item.romanKey || '')
        )
        .sort((a, b) => b.score - a.score)[0]
      if (evidenceWinner) {
        for (const item of scored) {
          if (
            item.tier === TIER_EXACT &&
            item.exactSource === 'strict' &&
            evidenceWinner.score >= item.score + 3 &&
            (evidenceWinner.validity.evidence || 0) >= (item.validity.evidence || 0) * 4.25
          ) {
            item.tier = TIER_DICT
          }
        }
      }

      const ranked = modRankCandidates(
        scored,
        { roman: lower, limit: 0 },
        runtimePolicy,
        enableUserLm ? USER_LEARNING : null
      )

      // User LM is learned on commit only (see learnCommittedChoice / commit_on_punct).
      void enableUserLm

      // The pure layout API owns the fixed GU #1 → Latin #2 contract.
      const menuPolicy = runtimePolicy.menu || {}
      const laid = modLayoutMenu(ranked, {
        includeLatin,
        latinText: input,
        maxGujaratiBeforeEmoji: Number(menuPolicy.max_gujarati_before_emoji) || 3,
        maxEmoji,
        emojiMinConfidence: Number(menuPolicy.emoji_min_confidence) || 0.9,
      })

      const descriptors = laid.map((item, rank) => {
        // TIER_EMOJI=TIER_MAX → base 0 so script candidates always outrank emoji.
        const descriptor = {
          candidateType: item.candidateType || 'gujarati',
          native: item.native,
          comment: item.comment || '',
          quality: (TIER_MAX - item.tier) * 200 + Math.max(0, 180 - rank),
        }
        if (getEnvBool(env, 'translator/debug_rank', false)) {
          const debugRank = {
            tier: item.tier,
            score: item.score,
            romanKey: item.romanKey,
            source: item.exactSource,
            weight: item.weight,
            evidence: item.validity && item.validity.evidence,
            transformCost: item.transformCost,
          }
          if (item.neuralSeen && Number.isFinite(item.neuralRelativeLogProb)) {
            debugRank.neuralRelativeLogProb = item.neuralRelativeLogProb
          }
          descriptor.debugRank = debugRank
        }
        return descriptor
      })

      // Hard cap menu size (page_size alone still allows paging past soft limits).
      const capped = descriptors.length > maxCandidates
        ? descriptors.slice(0, maxCandidates)
        : descriptors
      this.menuCache.set(cacheKey, capped)
      if (this.menuCache.size > 512) this.menuCache.delete(this.menuCache.keys().next().value)
      return materialize(capped)
    } catch (e) {
      console.error('$qjs$ translate error:', e.message)
      return []
    }
  }
}


// --- Plan P3 public ranking API ---
export function generateCandidates(roman, runtime, policy) {
  return modGenerateCandidates(roman, runtime, policy)
}

export function rankCandidates(records, context, policy, learning) {
  return modRankCandidates(records, context, policy, learning)
}

export function layoutMenu(records, opts) {
  return modLayoutMenu(records, opts)
}

export function rankRomanTopTexts(roman, maxN) {
  // Offline helper — uses in-memory lexicon maps already loaded in process.
  maxN = maxN || 6
  try {
    const forms = expandRomanQueries(String(roman || '').toLowerCase())
    const texts = []
    const seen = new Set()
    for (const q of forms) {
      const hit = nativeLexHit(q) || (typeof LEXICON !== 'undefined' && LEXICON && LEXICON.get && LEXICON.get(q))
      const native = hit && (hit.native || hit)
      if (!native || seen.has(native)) continue
      seen.add(native)
      texts.push(native)
      if (texts.length >= maxN) break
    }
    return texts
  } catch (_e) {
    return []
  }
}
