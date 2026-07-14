/**
 * Ranking core — tiers, CandidateRecord, menu layout, coefficient hooks.
 * Authoritative for source-aware macOS-style ordering.
 */
import { EXPLICIT_PROMOTION_THRESHOLD } from './learning.js'
import { expandRomanLattice } from './phonetic.js'
import { nativeEvidenceLookup, trieFind } from './storage.js'

export const RANKING_MODULE = 2

export const TIER_PERSONALIZED = -1
export const TIER_EXACT = 0
export const TIER_DICT = 1
export const TIER_PHONETIC = 2
export const TIER_LATIN = 3
export const TIER_PREFIX = 4
export const TIER_EMOJI = 5
export const TIER_MAX = 5

export const LEXICON_STRONG_WEIGHT = 100

/** @typedef {'strong_exact'|'soft_exact'|'fuzzy'|'near_exact'|'stem_derived'|'phonetic'|'prefix'|'emoji'|'latin'} CandidateSource */

/**
 * @returns {{native:string,romanKey:string,source:string,weight:number,transformCost:number,uni:number,stem:number,attested:boolean,userCount:number,score:number,displayGroup:string,tier:number}}
 */
export function makeCandidateRecord(partial) {
  return Object.assign(
    {
      native: '',
      romanKey: '',
      source: 'phonetic',
      weight: 0,
      transformCost: 0,
      uni: 0,
      stem: 0,
      attested: false,
      userCount: 0,
      score: 0,
      displayGroup: 'gu',
      tier: TIER_DICT,
    },
    partial || {}
  )
}

export function sourceToDisplayGroup(source) {
  if (source === 'prefix') return 'prefix'
  if (source === 'emoji') return 'emoji'
  if (source === 'latin') return 'latin'
  return 'gu'
}

/** Map lexicon hit → tier. Soft / stem_derived never get TIER_EXACT. */
export function lexiconHitTier(source, weight, typedRoman, hitRoman, opts) {
  const w = Number(weight) || 0
  const soft = w > 0 && w < LEXICON_STRONG_WEIGHT
  const iastPair = (opts && opts.iastPlacePair) || {}
  if (typedRoman && typedRoman.length === 1 && iastPair[typedRoman]) return TIER_DICT
  if (source === 'strict' && !soft) return TIER_EXACT
  if (soft) return TIER_DICT
  if (source === 'stem_matra' || source === 'stem_postfix' || source === 'stem_derived') {
    return TIER_DICT
  }
  if (source === 'near_exact') {
    if (opts && opts.typedHasLexEntry) return TIER_DICT
    return TIER_EXACT
  }
  if (source === 'fuzzy' || source === 'strict') return TIER_EXACT
  return TIER_DICT
}

/**
 * macOS menu layout after linguistic rank:
 * GU #1 → Latin echo #2 → remaining GU → prefix → emoji.
 */
export function layoutMenu(records, opts) {
  const includeLatin = !opts || opts.includeLatin !== false
  const latinText = (opts && opts.latinText) || ''
  const gu = []
  const latin = []
  const prefix = []
  const emoji = []
  for (const r of records) {
    if (r.tier === TIER_LATIN || r.source === 'latin' || r.displayGroup === 'latin') latin.push(r)
    else if (r.tier === TIER_PREFIX || r.source === 'prefix') prefix.push(r)
    else if (r.tier === TIER_EMOJI || r.source === 'emoji') emoji.push(r)
    else gu.push(r)
  }
  const laid = []
  if (gu.length) {
    laid.push(gu[0])
    if (includeLatin) {
      if (latin.length) laid.push(latin[0])
      else if (latinText) {
        laid.push(
          makeCandidateRecord({
            native: latinText,
            romanKey: String(latinText).toLowerCase(),
            source: 'latin',
            displayGroup: 'latin',
            tier: TIER_LATIN,
          })
        )
      }
    }
    for (let i = 1; i < gu.length; i++) laid.push(gu[i])
  } else if (includeLatin && (latin.length || latinText)) {
    laid.push(
      latin[0] ||
        makeCandidateRecord({
          native: latinText,
          source: 'latin',
          displayGroup: 'latin',
          tier: TIER_LATIN,
        })
    )
  }
  for (const x of prefix) laid.push(x)
  for (const x of emoji) laid.push(x)
  return laid
}

/** Dot-product score from optional coefficient JSON (Phase G). */
export function applyLinearCoefficients(features, coefficients) {
  if (!coefficients || !coefficients.weights) return 0
  let s = coefficients.bias || 0
  for (const [k, w] of Object.entries(coefficients.weights)) {
    s += (features[k] || 0) * w
  }
  return s
}

export const DEFAULT_POLICY = {
  version: 2,
  tiers: {
    exact: 0,
    dict: 1,
    phonetic: 2,
    latin: 3,
    prefix: 4,
    emoji: 5,
    personalized: -1,
  },
  menu: { latin_position: 2, max_candidates: 6 },
  lattice: { beam: 64 },
}

export function loadPolicyFromText(text) {
  try {
    return Object.assign({}, DEFAULT_POLICY, JSON.parse(text))
  } catch (_e) {
    return DEFAULT_POLICY
  }
}

export function generateCandidates(roman, runtime, policy) {
  const typed = String(roman || '').toLowerCase()
  if (!typed || !runtime) return []
  const lattice = expandRomanLattice(
    typed,
    (policy && policy.confusion_pairs) || null,
    (policy && policy.lattice) || null
  )
  const records = []
  const seen = new Set()
  for (const form of lattice) {
    const hit = trieFind(runtime, form.roman)
    if (!hit || !hit.native || seen.has(hit.native)) continue
    seen.add(hit.native)
    const evidence = nativeEvidenceLookup(runtime, hit.native)
    const source = form.roman === typed ? 'strict' : 'fuzzy'
    records.push(
      makeCandidateRecord({
        native: hit.native,
        text: hit.native,
        romanKey: form.roman,
        source,
        weight: Number(hit.weight) || 0,
        transformCost: form.cost || 0,
        uni: evidence.unigram || 0,
        stem: evidence.stem || 0,
        attested: !!evidence.attested,
        tier: lexiconHitTier(source, hit.weight, typed, form.roman),
      })
    )
  }
  return records
}

export function rankCandidates(records, context, policy, learning) {
  const pref =
    learning && context && context.roman
      ? learning.choices &&
        learning.choices[String(context.roman).toLowerCase()] &&
        learning.choices[String(context.roman).toLowerCase()].preferred_native
      : null
  const sorted = (records || []).slice().sort((a, b) => {
    if (pref) {
      if (a.native === pref || a.text === pref) return -1
      if (b.native === pref || b.text === pref) return 1
    }
    return (a.tier || 0) - (b.tier || 0) || (b.score || 0) - (a.score || 0)
  })
  const max = Math.max(1, Number(policy && policy.menu && policy.menu.max_candidates) || 6)
  return sorted.slice(0, max)
}

export { EXPLICIT_PROMOTION_THRESHOLD }

/** Onset-only long-a demotion (parkhavyu family). */
export function onsetOnlyLongAPenalty(lower, text, penalty) {
  if (!/^(?:[kgcjtdTDpbnmylrsvwxyz]|ch|kh|gh|jh|th|dh|ph|bh|sh|Sh|tr|dr)a(?!a)/i.test(lower)) {
    return 0
  }
  const leadLong = text.startsWith('આ') || /^[\u0A95-\u0AB9]\u0ABE/.test(text)
  if (!leadLong) return 0
  const rest = text.startsWith('આ') ? text.slice(1) : text.slice(2)
  if (!rest.includes('ા') && /a(?!a)/.test(lower.slice(2))) return -(penalty || 3.8)
  return 0
}
