/** Optional offline Gujarati n-best bridge. The deterministic engine remains complete without it. */

const GUJARATI_WORD = /^[\u0A80-\u0AFF\u200C\u200D]+$/u

export function neuralCapability(env) {
  if (env && typeof env.transliterateNBest === 'function') {
    if (
      typeof env.gujaratiModelAvailable === 'function' &&
      !env.gujaratiModelAvailable()
    ) {
      return { available: false, provider: null }
    }
    return { available: true, provider: 'environment' }
  }
  if (
    typeof globalThis !== 'undefined' &&
    globalThis.GujaratiModel &&
    typeof globalThis.GujaratiModel.nbest === 'function'
  ) {
    return { available: true, provider: 'global' }
  }
  return { available: false, provider: null }
}

export function neuralNBest(env, roman, limit, mode) {
  const configuredMode = String(mode || 'auto').toLowerCase()
  if (configuredMode === 'off') return { candidates: [], capability: neuralCapability(env) }
  const capability = neuralCapability(env)
  if (!capability.available) {
    return { candidates: [], capability, requiredMissing: configuredMode === 'required' }
  }
  const max = Math.max(1, Math.min(8, Number(limit) || 4))
  let raw = []
  try {
    raw = capability.provider === 'environment'
      ? env.transliterateNBest(String(roman || ''), max)
      : globalThis.GujaratiModel.nbest(String(roman || ''), max)
    if (typeof raw === 'string') raw = JSON.parse(raw)
    if (raw && raw.error) throw new Error(String(raw.error))
  } catch (error) {
    return { candidates: [], capability, error: String(error && error.message ? error.message : error) }
  }
  const seen = new Set()
  const candidates = []
  for (const item of Array.isArray(raw) ? raw : []) {
    const native = String(item && (item.native || item.text) || '')
    const logProb = Number(item && (item.logProb ?? item.log_probability ?? item.score))
    if (!native || !GUJARATI_WORD.test(native) || native.includes('\uFFFD') || seen.has(native)) continue
    if (!Number.isFinite(logProb)) continue
    seen.add(native)
    candidates.push({
      native,
      logProb,
      modelVersion: String((item && item.modelVersion) || 'unknown'),
    })
    if (candidates.length >= max) break
  }
  return { candidates, capability }
}
