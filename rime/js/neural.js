/** Optional offline Gujarati n-best bridge. The deterministic engine remains complete without it. */

const ROMAN_WORD = /^[a-z]+(?:[+'-][a-z]+)*$/
const GU_INDEPENDENT = /[\u0A85-\u0A94]/
const GU_CONSONANT = /[\u0A95-\u0AB9\u0AF9]/
const GU_MATRA = /[\u0ABE-\u0ACC\u0AE2\u0AE3]/
const GU_MODIFIER = /[\u0A81-\u0A83]/
const GU_NUKTA = '\u0ABC'
const GU_VIRAMA = '\u0ACD'
const GU_OM = '\u0AD0'
const ZWNJ = '\u200C'
const ZWJ = '\u200D'

/** Neural inference accepts words, never punctuation/number/mixed-script segments. */
export function isValidNeuralRomanInput(value) {
  const roman = String(value || '').toLowerCase()
  return roman.length > 0 && roman.length <= 32 && ROMAN_WORD.test(roman)
}

/** A strict Gujarati orthographic word validator for untrusted model output. */
export function isValidGujaratiModelOutput(value) {
  let text = String(value || '')
  try {
    if (typeof text.normalize === 'function') text = text.normalize('NFC')
  } catch (_e) {}
  if (!text || text.includes('\uFFFD')) return false
  if (text === GU_OM) return true

  let haveBase = false
  let baseIsConsonant = false
  let haveMatra = false
  let haveModifier = false
  let afterVirama = false
  let afterJoiner = false
  let afterNukta = false
  for (let index = 0; index < text.length; index += 1) {
    const ch = text[index]
    if (GU_INDEPENDENT.test(ch) || GU_CONSONANT.test(ch)) {
      if ((afterVirama || afterJoiner) && !GU_CONSONANT.test(ch)) return false
      haveBase = true
      baseIsConsonant = GU_CONSONANT.test(ch)
      haveMatra = false
      haveModifier = false
      afterVirama = false
      afterJoiner = false
      afterNukta = false
      continue
    }
    if (ch === GU_NUKTA) {
      if (!haveBase || !baseIsConsonant || haveMatra || haveModifier || afterVirama || afterNukta) return false
      afterNukta = true
      continue
    }
    if (ch === GU_VIRAMA) {
      if (!haveBase || !baseIsConsonant || haveMatra || haveModifier || afterVirama) return false
      afterVirama = true
      afterJoiner = false
      continue
    }
    if (ch === ZWJ || ch === ZWNJ) {
      if (!afterVirama || afterJoiner) return false
      afterJoiner = true
      continue
    }
    if (GU_MATRA.test(ch)) {
      if (!haveBase || !baseIsConsonant || haveMatra || haveModifier || afterVirama || afterJoiner) return false
      haveMatra = true
      continue
    }
    if (GU_MODIFIER.test(ch)) {
      if (!haveBase || haveModifier || afterVirama || afterJoiner) return false
      haveModifier = true
      continue
    }
    return false
  }
  return haveBase && !afterVirama && !afterJoiner
}

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
  const normalizedRoman = String(roman || '').toLowerCase()
  if (configuredMode === 'off') return { candidates: [], capability: neuralCapability(env) }
  const capability = neuralCapability(env)
  if (!isValidNeuralRomanInput(normalizedRoman)) {
    return { candidates: [], capability, invalidInput: true }
  }
  if (!capability.available) {
    return { candidates: [], capability, requiredMissing: configuredMode === 'required' }
  }
  const max = Math.max(1, Math.min(8, Number(limit) || 4))
  let raw = []
  try {
    raw = capability.provider === 'environment'
      ? env.transliterateNBest(normalizedRoman, max)
      : globalThis.GujaratiModel.nbest(normalizedRoman, max)
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
    if (!isValidGujaratiModelOutput(native) || seen.has(native)) continue
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
