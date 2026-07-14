/**
 * Ranking helpers consuming ranking_policy.json (pure scoring glue).
 */
export const DEFAULT_POLICY = {
  version: 1,
  tiers: { exact: 0, dict: 1, phonetic: 2, latin: 3, prefix: 4, emoji: 5, personalized: -1 },
  weights: {
    lexicon_strong: 100,
    user_learning_threshold: 2,
    user_roman_boost_at_threshold: 80,
    onset_only_long_a_penalty: 3.8,
  },
}

export function loadPolicyFromText(text) {
  try {
    return Object.assign({}, DEFAULT_POLICY, JSON.parse(text))
  } catch (_e) {
    return DEFAULT_POLICY
  }
}

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
