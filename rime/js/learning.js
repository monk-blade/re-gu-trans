/**
 * User learning v2 — explicit numbered selections only; prefer at count ≥ 3.
 * Persistence requires Environment.writeFileAtomic.
 */
export const LEARNING_FILE = 'gujarati.user-learning.json'
export const LEARNING_VERSION = 2
export const EXPLICIT_PROMOTION_THRESHOLD = 3
export const MAX_ROMANS = 10000
export const MAX_NATIVES_PER_ROMAN = 8
export const MAX_COUNT = 255

let SESSION_STORE = null
let SESSION_USER_DIR = null

export function emptyLearning() {
  return { version: LEARNING_VERSION, choices: {} }
}

export function normalizeRoman(roman) {
  return String(roman || '').toLowerCase().replace(/[^a-z+]/g, '')
}

/**
 * Migrate v1 → v2 without instant promotion.
 * Old counts become legacy metadata; explicit_count starts at 0; preferred_native unset.
 */
export function migrateLearning(data) {
  const store = emptyLearning()
  if (!data || typeof data !== 'object') return store
  const choices = data.choices || {}
  for (const [roman, nest] of Object.entries(choices)) {
    const r = normalizeRoman(roman)
    if (!r) continue
    if (!nest || typeof nest !== 'object') continue
    // v2 shape already?
    if (nest.natives || nest.preferred_native != null) {
      store.choices[r] = {
        preferred_native: nest.preferred_native || null,
        natives: {},
      }
      const natives = nest.natives || {}
      for (const [native, meta] of Object.entries(natives)) {
        store.choices[r].natives[native] = {
          explicit_count: Math.min(MAX_COUNT, Number(meta.explicit_count) || 0),
          last_used: Number(meta.last_used) || 0,
          legacy_count: Number(meta.legacy_count || meta.count) || 0,
        }
      }
      continue
    }
    // v1: nest is { native: { count, last_used } }
    store.choices[r] = { preferred_native: null, natives: {} }
    for (const [native, meta] of Object.entries(nest)) {
      if (!meta || typeof meta !== 'object') continue
      store.choices[r].natives[native] = {
        explicit_count: 0,
        last_used: Number(meta.last_used) || 0,
        legacy_count: Math.min(MAX_COUNT, Number(meta.count) || 0),
      }
    }
  }
  return store
}

export function parseLearning(text) {
  try {
    const data = JSON.parse(text || '{}')
    if (!data || typeof data !== 'object') return emptyLearning()
    if (Number(data.version) >= 2) {
      const store = migrateLearning(data)
      store.version = LEARNING_VERSION
      return store
    }
    return migrateLearning(data)
  } catch (_e) {
    return emptyLearning()
  }
}

function ensureRoman(store, roman) {
  const r = normalizeRoman(roman)
  if (!store.choices[r]) store.choices[r] = { preferred_native: null, natives: {} }
  if (!store.choices[r].natives) store.choices[r].natives = {}
  return store.choices[r]
}

function pruneStore(store) {
  for (const [r, entry] of Object.entries(store.choices)) {
    const natives = entry.natives || {}
    const entries = Object.entries(natives).sort(
      (a, b) => (b[1].last_used || 0) - (a[1].last_used || 0)
    )
    if (entries.length > MAX_NATIVES_PER_ROMAN) {
      entry.natives = Object.fromEntries(entries.slice(0, MAX_NATIVES_PER_ROMAN))
      if (entry.preferred_native && !entry.natives[entry.preferred_native]) {
        entry.preferred_native = null
      }
    }
  }
  const romans = Object.keys(store.choices)
  if (romans.length > MAX_ROMANS) {
    const scored = romans
      .map((key) => {
        const natives = store.choices[key].natives || {}
        const maxLast = Math.max(0, ...Object.values(natives).map((x) => x.last_used || 0))
        return [key, maxLast]
      })
      .sort((a, b) => a[1] - b[1])
    for (let i = 0; i < scored.length - MAX_ROMANS; i++) delete store.choices[scored[i][0]]
  }
  return store
}

/**
 * Record an explicit numbered Gujarati selection (not Space/punct/Latin/emoji).
 * On the third explicit selection of the same pair, set preferred_native.
 * Promotion applies on the *next* composition (caller must not reorder current commit).
 */
export function recordExplicitSelection(store, roman, native, nowMs) {
  const normalized = normalizeRoman(roman)
  if (!normalized || !native) return store
  if (!/[\u0A80-\u0AFF]/.test(native)) return store
  if (/[\u{1F300}-\u{1FAFF}]/u.test(native)) return store
  const entry = ensureRoman(store, normalized)
  const cur = entry.natives[native] || { explicit_count: 0, last_used: 0, legacy_count: 0 }
  cur.explicit_count = Math.min(MAX_COUNT, (cur.explicit_count || 0) + 1)
  cur.last_used = nowMs || Date.now()
  entry.natives[native] = cur
  if (cur.explicit_count >= EXPLICIT_PROMOTION_THRESHOLD) {
    entry.preferred_native = native
  }
  return pruneStore(store)
}

export function preferredNative(store, roman) {
  if (!store || !roman) return null
  const entry = store.choices[normalizeRoman(roman)]
  return (entry && entry.preferred_native) || null
}

export function explicitCount(store, roman, native) {
  const entry = store && store.choices && store.choices[normalizeRoman(roman)]
  if (!entry || !entry.natives || !entry.natives[native]) return 0
  return entry.natives[native].explicit_count || 0
}

/** Tie-break frequency (legacy + explicit); never triggers prefer alone. */
export function choiceCount(store, roman, native) {
  const entry = store && store.choices && store.choices[normalizeRoman(roman)]
  if (!entry || !entry.natives || !entry.natives[native]) return 0
  const m = entry.natives[native]
  return (m.explicit_count || 0) + (m.legacy_count || 0)
}

export function loadLearning(env) {
  if (!env || typeof env.loadFile !== 'function') return emptyLearning()
  try {
    const base = env.userDataDir
      ? String(env.userDataDir).replace(/\/$/, '').replace(/\\$/, '') + '/'
      : ''
    return parseLearning(env.loadFile(base + LEARNING_FILE) || '{}')
  } catch (_e) {
    return emptyLearning()
  }
}

/** Shared module-scoped store used by processor and translator in one QJS runtime. */
export function initLearningSession(env) {
  const userDir = env && env.userDataDir ? String(env.userDataDir) : ''
  if (!SESSION_STORE || SESSION_USER_DIR !== userDir) {
    SESSION_STORE = loadLearning(env)
    SESSION_USER_DIR = userDir
  }
  return SESSION_STORE
}

export function getLearningSession(env) {
  return SESSION_STORE || initLearningSession(env)
}

export function recordExplicitSelectionForSession(env, roman, native, nowMs) {
  const current = getLearningSession(env)
  const next = parseLearning(JSON.stringify(current))
  recordExplicitSelection(next, roman, native, nowMs)
  if (!persistLearningAtomic(env, next, LEARNING_FILE)) return { ok: false, store: current }
  SESSION_STORE = next
  return { ok: true, store: next }
}

export function resetLearningSessionForTests() {
  SESSION_STORE = null
  SESSION_USER_DIR = null
}

export function persistLearningAtomic(env, store, relativePath) {
  const path = relativePath || LEARNING_FILE
  if (!env || typeof env.writeFileAtomic !== 'function') {
    console.log('$qjs$ learning disabled: Environment.writeFileAtomic missing')
    return false
  }
  try {
    const out = Object.assign({}, store, { version: LEARNING_VERSION })
    env.writeFileAtomic(path, JSON.stringify(out))
    return true
  } catch (e) {
    console.log('$qjs$ writeFileAtomic failed: ' + (e && e.message))
    return false
  }
}

export function isLearningEnabled(getBool, capabilities) {
  const schemaOn =
    typeof getBool === 'function'
      ? getBool('translator/enable_user_learning', getBool('translator/enable_user_lm', true))
      : true
  if (!schemaOn) return false
  if (capabilities && capabilities.writeFileAtomic === false) return false
  return true
}

export function checkLearningCapability(env) {
  if (env && typeof env.writeFileAtomic === 'function') return { ok: true }
  console.log('$qjs$ learning disabled: Environment.writeFileAtomic missing')
  return { ok: false }
}
