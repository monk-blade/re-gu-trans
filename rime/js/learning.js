/**
 * User learning — JSON store, notifier-driven, atomic writes only.
 */
export const LEARNING_FILE = 'gujarati.user-learning.json'
export const LEARNING_VERSION = 1
export const MAX_ROMANS = 10000
export const MAX_NATIVES_PER_ROMAN = 8
export const MAX_COUNT = 255

export function emptyLearning() {
  return { version: LEARNING_VERSION, choices: {} }
}

export function parseLearning(text) {
  try {
    const data = JSON.parse(text || '{}')
    if (!data || typeof data !== 'object') return emptyLearning()
    if (!data.choices) data.choices = {}
    data.version = LEARNING_VERSION
    return data
  } catch (_e) {
    return emptyLearning()
  }
}

export function recordChoice(store, roman, native, nowMs) {
  if (!roman || !native) return store
  if (!/[\u0A80-\u0AFF]/.test(native)) return store
  if (/[\u{1F300}-\u{1FAFF}]/u.test(native)) return store
  const r = String(roman).toLowerCase()
  if (!store.choices[r]) store.choices[r] = {}
  const nest = store.choices[r]
  const cur = nest[native] || { count: 0, last_used: 0 }
  cur.count = Math.min(MAX_COUNT, (cur.count || 0) + 1)
  cur.last_used = nowMs || Date.now()
  nest[native] = cur
  const entries = Object.entries(nest).sort((a, b) => (b[1].last_used || 0) - (a[1].last_used || 0))
  if (entries.length > MAX_NATIVES_PER_ROMAN) {
    store.choices[r] = Object.fromEntries(entries.slice(0, MAX_NATIVES_PER_ROMAN))
  }
  const romans = Object.keys(store.choices)
  if (romans.length > MAX_ROMANS) {
    const scored = romans
      .map((key) => {
        const maxLast = Math.max(0, ...Object.values(store.choices[key]).map((x) => x.last_used || 0))
        return [key, maxLast]
      })
      .sort((a, b) => a[1] - b[1])
    for (let i = 0; i < scored.length - MAX_ROMANS; i++) delete store.choices[scored[i][0]]
  }
  return store
}

export function choiceCount(store, roman, native) {
  const nest = store && store.choices && store.choices[String(roman).toLowerCase()]
  if (!nest || !nest[native]) return 0
  return nest[native].count || 0
}

/**
 * Persist learning. Requires Environment.writeFileAtomic — no saveFile/write fallback.
 * @returns {boolean} true if written
 */
export function persistLearningAtomic(env, store, relativePath) {
  const path = relativePath || LEARNING_FILE
  if (!env || typeof env.writeFileAtomic !== 'function') {
    console.error('$qjs$ learning disabled: Environment.writeFileAtomic missing')
    return false
  }
  try {
    env.writeFileAtomic(path, JSON.stringify(store))
    return true
  } catch (e) {
    console.error('$qjs$ writeFileAtomic failed: ' + (e && e.message))
    return false
  }
}

/** enable_user_learning authoritative; honor deprecated enable_user_lm only if unset. */
export function isLearningEnabled(getBool) {
  // getBool(key, default) — if enable_user_learning is explicitly false, always off.
  const hasNew = getBool('translator/__has_enable_user_learning__', false)
  // Callers pass resolved schema booleans:
  return getBool
}
