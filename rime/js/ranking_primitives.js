/**
 * Pure ranking primitives — records, tiers, layout, and coefficient hooks.
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
 * @returns {{typedRoman:string,queryRoman:string,native:string,romanKey:string,source:string,provenance:string[],transformFamily:string,weight:number,transformCost:number,unigram:number,uni:number,stem:number,attested:boolean,neuralLogProb:number,personalizationCount:number,userCount:number,score:number,displayGroup:string,tier:number}}
 */
export function makeCandidateRecord(partial) {
  return Object.assign(
    {
      native: '',
      typedRoman: '',
      queryRoman: '',
      romanKey: '',
      source: 'phonetic',
      provenance: [],
      paths: [],
      transformFamily: 'typed',
      weight: 0,
      transformCost: 0,
      deterministicTransformCost: Infinity,
      unigram: 0,
      uni: 0,
      stem: 0,
      attested: false,
      neuralLogProb: 0,
      neuralRawLogProb: -Infinity,
      neuralRelativeLogProb: -Infinity,
      neuralSeen: false,
      neuralRank: Infinity,
      neuralModelVersion: '',
      modelCoreAgreement: false,
      personalizationCount: 0,
      userCount: 0,
      score: 0,
      displayGroup: 'gu',
      tier: TIER_DICT,
    },
    partial || {}
  )
}

/** One source-independent route by which a native candidate was discovered. */
export function makeCandidatePath(partial) {
  return Object.assign(
    {
      source: 'phonetic',
      queryRoman: '',
      transformFamily: 'typed',
      transformCost: 0,
      lexiconWeight: 0,
      tier: TIER_PHONETIC,
      isNeural: false,
      neuralRank: Infinity,
      neuralRawLogProb: -Infinity,
      neuralRelativeLogProb: -Infinity,
      modelVersion: '',
      comment: '',
      closeness: 0,
    },
    partial || {}
  )
}

function pathIdentity(path) {
  return [
    path.source,
    path.queryRoman,
    path.transformFamily,
    Number(path.transformCost) || 0,
    Number(path.lexiconWeight) || 0,
    path.isNeural ? 1 : 0,
    Number.isFinite(path.neuralRank) ? path.neuralRank : '',
    Number.isFinite(path.neuralRawLogProb) ? path.neuralRawLogProb : '',
    path.modelVersion || '',
  ].join('\u001f')
}

function sourcePriority(source) {
  if (source === 'strict') return 0
  if (source === 'near_exact') return 1
  if (source === 'fuzzy') return 2
  if (String(source).startsWith('stem_')) return 3
  if (source === 'lexicon') return 4
  if (source === 'phonetic') return 5
  if (source === 'prefix') return 6
  if (source === 'emoji') return 7
  return 8
}

/**
 * Merge a discovery path without making rank depend on insertion order.
 * Native evidence is deliberately not accepted here; storage owns it.
 */
export function mergeCandidatePath(record, partialPath) {
  const path = makeCandidatePath(partialPath)
  if (!Array.isArray(record.paths)) record.paths = []
  const identity = pathIdentity(path)
  if (!record.paths.some((item) => pathIdentity(item) === identity)) record.paths.push(path)

  const paths = record.paths
  const deterministic = paths.filter((item) => !item.isNeural)
  const neural = paths.filter((item) => item.isNeural)
  const strongest = deterministic.slice().sort((a, b) =>
    (a.tier - b.tier) ||
    (sourcePriority(a.source) - sourcePriority(b.source)) ||
    (a.transformCost - b.transformCost) ||
    (b.lexiconWeight - a.lexiconWeight) ||
    (b.closeness - a.closeness) ||
    String(a.source).localeCompare(String(b.source))
  )[0]

  record.provenance = Array.from(new Set(paths.map((item) => item.source))).sort()
  record.weight = strongest ? Number(strongest.lexiconWeight) || 0 : 0
  record.deterministicTransformCost = deterministic.length
    ? Math.min(...deterministic.map((item) => Math.max(0, Number(item.transformCost) || 0)))
    : Infinity
  record.transformCost = strongest ? Math.max(0, Number(strongest.transformCost) || 0) : 0
  if (strongest) {
    record.tier = strongest.tier
    record.source = strongest.source
    record.exactSource = strongest.source
    record.queryRoman = strongest.queryRoman || record.queryRoman
    record.romanKey = strongest.queryRoman || record.romanKey
    record.transformFamily = strongest.transformFamily || record.transformFamily
    record.closeness = strongest.closeness
    record.comment = strongest.comment || record.comment
  } else if (neural.length) {
    record.tier = Math.min(...neural.map((item) => Math.max(TIER_DICT, item.tier)))
    record.source = 'neural'
    record.exactSource = 'neural'
    record.transformFamily = 'neural'
    record.comment = neural[0].comment || 'model'
  }

  record.neuralSeen = neural.length > 0
  record.neuralRank = neural.reduce(
    (best, item) => Math.min(best, Number.isFinite(item.neuralRank) ? item.neuralRank : Infinity),
    Infinity
  )
  record.neuralRawLogProb = neural.reduce(
    (best, item) => Math.max(best, item.neuralRawLogProb),
    -Infinity
  )
  record.neuralRelativeLogProb = neural.reduce(
    (best, item) => Math.max(best, item.neuralRelativeLogProb),
    -Infinity
  )
  record.neuralLogProb = Number.isFinite(record.neuralRelativeLogProb)
    ? record.neuralRelativeLogProb
    : 0
  record.neuralModelVersion = neural
    .slice()
    .sort((a, b) => (a.neuralRank - b.neuralRank))[0]?.modelVersion || ''
  record.modelCoreAgreement = neural.length > 0 && deterministic.length > 0
  return record
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
  if (source === 'stem_matra' || source === 'stem_postfix' || source === 'stem_derived' || source === 'stem_inflection' || source === 'stem_compound') {
    return TIER_DICT
  }
  if (source === 'near_exact') {
    if (opts && opts.typedHasLexEntry) return TIER_DICT
    return TIER_EXACT
  }
  // A transformed query is evidence, never an exact user spelling. Its
  // lexicon weight may rank it inside the evidence tier but cannot erase the
  // transform that produced it (ko must not become exact kau → કાઉ).
  if (source === 'fuzzy') return TIER_DICT
  if (source === 'strict') return TIER_EXACT
  return TIER_DICT
}

/**
 * macOS menu layout after linguistic rank:
 * GU #1 → Latin echo #2 → bounded strong GU → confident emoji → remaining GU → prefix.
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
  const maxGujaratiBeforeEmoji = Math.max(
    1,
    Number(opts && opts.maxGujaratiBeforeEmoji) || Number.MAX_SAFE_INTEGER
  )
  const maxEmoji = Math.max(0, Number(opts && opts.maxEmoji) || emoji.length)
  const emojiMinConfidence = Number(opts && opts.emojiMinConfidence) || 0
  const eligibleEmoji = emoji
    .filter((item) => Number(item.emojiConfidence || item.confidence || 0) >= emojiMinConfidence)
    .slice(0, maxEmoji)
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
    let i = 1
    while (i < gu.length && i < maxGujaratiBeforeEmoji) {
      laid.push(gu[i])
      i += 1
    }
    for (const item of eligibleEmoji) laid.push(item)
    for (; i < gu.length; i += 1) laid.push(gu[i])
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
  const emittedEmoji = new Set(eligibleEmoji)
  for (const x of emoji) if (!emittedEmoji.has(x)) laid.push(x)
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
        typedRoman: typed,
        queryRoman: form.roman,
        romanKey: form.roman,
        source,
        provenance: [source],
        transformFamily: form.family || (source === 'strict' ? 'typed' : 'fuzzy'),
        weight: Number(hit.weight) || 0,
        transformCost: form.cost || 0,
        unigram: evidence.unigram || 0,
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
    return (
      (a.tier || 0) - (b.tier || 0) ||
      (b.score || 0) - (a.score || 0) ||
      (b.closeness || 0) - (a.closeness || 0) ||
      (b.weight || 0) - (a.weight || 0) ||
      (a.index || 0) - (b.index || 0)
    )
  })
  if (context && context.limit === 0) return sorted
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
