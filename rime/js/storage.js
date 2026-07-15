/**
 * Runtime storage — sole authority for lexicon / prefix / native evidence.
 * Host Trie via globalThis.Trie only. Text fallback requires allowTextFallback=true.
 */
export const STORAGE_VERSION = 5

export function assetPaths(userDataDir) {
  const base = userDataDir ? String(userDataDir).replace(/\/$/, '').replace(/\\$/, '') : null
  const join = (rel) => (base ? base + '/' + rel : rel)
  return {
    lexiconBin: [join('js/lexicon.trie.bin'), 'js/lexicon.trie.bin'],
    prefixBin: [join('js/prefix.trie.bin'), 'js/prefix.trie.bin'],
    prefixText: [join('js/prefix.trie.txt'), 'js/prefix.trie.txt'],
    nativeLmBin: [join('js/native_lm.trie.bin'), 'js/native_lm.trie.bin'],
    nativeLmMeta: [join('js/native_lm_meta.json'), 'js/native_lm_meta.json'],
    exceptions: [join('js/exceptions.json'), 'js/exceptions.json'],
    emoji: [join('js/emoji_keywords.json'), 'js/emoji_keywords.json'],
    policy: [join('js/ranking_policy.json'), 'js/ranking_policy.json'],
    lexiconBlob: [join('js/gu_lexicon_blob.json'), 'js/gu_lexicon_blob.json'],
    unigram: [join('js/lm/unigram.tsv'), 'js/lm/unigram.tsv'],
    stems: [join('js/lm/stems.json'), 'js/lm/stems.json'],
    attested: [join('js/lm/attested.json'), 'js/lm/attested.json'],
  }
}

/** @deprecated */
export function lexiconPaths(userDataDir) {
  return assetPaths(userDataDir).lexiconBlob
}

/** @deprecated */
export function lmPaths(userDataDir) {
  return assetPaths(userDataDir)
}

function hostTrieCtor() {
  if (typeof globalThis !== 'undefined' && typeof globalThis.Trie === 'function') return globalThis.Trie
  return null
}

export function hostTrieAvailable() {
  return !!hostTrieCtor()
}

export function tryLoadNativeTrie(env, relativePath, preferBinary, injectedCtor) {
  const Ctor = injectedCtor || hostTrieCtor()
  if (!Ctor) return null
  try {
    const trie = new Ctor()
    const root =
      env && env.userDataDir ? String(env.userDataDir).replace(/\/$/, '').replace(/\\$/, '') + '/' : ''
    const abs = root + relativePath
    if (preferBinary !== false && typeof trie.loadBinaryFile === 'function') {
      const bin = abs.endsWith('.bin')
        ? abs
        : abs.replace(/\.txt$/, '.bin').replace(/\.tsv$/, '.trie.bin')
      try {
        trie.loadBinaryFile(bin)
        return trie
      } catch (_e) {}
    }
    if (typeof trie.loadTextFile === 'function' && /\.(txt|tsv)$/.test(abs)) {
      trie.loadTextFile(abs)
      return trie
    }
  } catch (e) {
    console.log('$qjs$ trie load skipped: ' + (e && e.message))
  }
  return null
}

function loadJson(load, paths) {
  for (const p of paths) {
    try {
      const raw = load(p)
      if (!raw) continue
      return JSON.parse(raw)
    } catch (_e) {}
  }
  return null
}

function loadExceptions(load, paths) {
  const out = new Map()
  const data = loadJson(load, paths)
  if (!data) return out
  const src = data.exceptions || data
  for (const [k, v] of Object.entries(src || {})) out.set(String(k).toLowerCase(), v)
  return out
}

function rememberEmoji(map, key, emoji, weight, metadata) {
  if (!key || !emoji) return
  const list = map.get(key) || []
  const existing = list.find((item) => item.e === emoji)
  const confidence = Math.max(0, Math.min(1, Number(metadata && metadata.confidence) || 0))
  if (existing) {
    existing.w = Math.max(existing.w, weight)
    existing.confidence = Math.max(existing.confidence || 0, confidence)
  } else {
    list.push({
      e: emoji,
      w: weight,
      confidence,
      source: String((metadata && metadata.source) || 'legacy'),
      category: String((metadata && metadata.category) || 'semantic'),
    })
  }
  list.sort((a, b) => b.confidence - a.confidence || b.w - a.w)
  map.set(key, list)
}

function lexiconNative(lexicon, key) {
  if (!lexicon || !key) return null
  if (lexicon.trie && typeof lexicon.trie.find === 'function') {
    try {
      const raw = lexicon.trie.find(key)
      return raw == null ? null : String(raw).split('\x1f')[0]
    } catch (_e) { return null }
  }
  return lexicon.map && lexicon.map.get(key)
}

function loadEmojiStorage(load, paths, lexicon) {
  const byRoman = new Map()
  const byNative = new Map()
  const data = loadJson(load, paths)
  const keywords = data && data.version === 2 ? data.keywords : data
  for (const [code, items] of Object.entries(keywords || {})) {
    const roman = String(code || '').toLowerCase()
    if (!roman || !Array.isArray(items)) continue
    for (const item of items) {
      const emoji = item && (item.e || item.emoji || item[0])
      const rawWeight = Number((item && (item.w || item.weight || item[1])) || 100)
      const weight = Number.isFinite(rawWeight) ? rawWeight : 100
      if (!emoji) continue
      rememberEmoji(byRoman, roman, String(emoji), weight, item)
      const native = lexiconNative(lexicon, roman)
      // Reverse native lookup is safe only for Gujarati-curated semantics.
      // English aliases such as club/art can collide with unrelated Gujarati
      // lexicon forms and create surprising emoji on ordinary roman input.
      if (native && (!item || item.source === 'curated_gu' || item.source === 'gu_extra')) {
        rememberEmoji(byNative, native, String(emoji), weight, item)
      }
      for (const nativeKeyword of (item && item.native_keywords) || []) {
        rememberEmoji(byNative, String(nativeKeyword), String(emoji), weight, item)
      }
    }
  }
  return { byRoman, byNative }
}

/**
 * Parse native_lm payload: "unigram\\tstem\\tattestedFlag"
 * @returns {{unigram:number,stem:number,attested:boolean}}
 */
export function parseNativeLmPayload(raw) {
  if (raw == null || raw === '') {
    return { unigram: 0, stem: 0, attested: false, present: false }
  }
  const s = String(raw)
  // Prefer tab-separated (binary build format); also accept \x1f
  const parts = s.includes('\t') ? s.split('\t') : s.split('\x1f')
  const unigram = Number(parts[0]) || 0
  const stem = Number(parts[1]) || 0
  const attRaw = parts[2]
  const attested = attRaw === '1' || attRaw === 1 || attRaw === true || attRaw === 'true'
  return { unigram, stem, attested, present: true }
}

/**
 * Structured native evidence from native_lm.trie.bin (or text Maps in dev).
 */
export function nativeEvidenceLookup(runtime, native) {
  const empty = { unigram: 0, stem: 0, attested: false, present: false }
  if (!native || !runtime) return empty
  const nat = runtime.nativeLm || {}
  if (nat.trie && typeof nat.trie.find === 'function') {
    try {
      const hit = nat.trie.find(native)
      if (hit == null) return empty
      return parseNativeLmPayload(hit)
    } catch (_e) {
      return empty
    }
  }
  if (nat.map && nat.map.has && nat.map.has(native)) {
    return parseNativeLmPayload(nat.map.get(native))
  }
  // Dev text maps
  const uni = (nat.unigramMap && nat.unigramMap.get(native)) || 0
  const stem = (nat.stemMap && nat.stemMap.get(native)) || 0
  const attested = !!(nat.attestedSet && nat.attestedSet.has(native))
  return {
    unigram: Number(uni) || 0,
    stem: Number(stem) || 0,
    attested,
    present:
      !!(nat.unigramMap && nat.unigramMap.has(native)) ||
      !!(nat.stemMap && nat.stemMap.has(native)) ||
      !!(nat.attestedSet && nat.attestedSet.has(native)) ||
      !!(nat.lexiconNativeSet && nat.lexiconNativeSet.has(native)),
  }
}

function loadTextPrefixIndex(load, paths) {
  const map = new Map()
  for (const path of paths) {
    try {
      const raw = load(path)
      if (!raw) continue
      for (const line of String(raw).split('\n')) {
        if (!line) continue
        const tab = line.indexOf('\t')
        if (tab < 1) continue
        const key = line.slice(0, tab)
        const payload = line.slice(tab + 1)
        const existing = map.get(key)
        map.set(key, existing ? existing + '\x1e' + payload : payload)
      }
      break
    } catch (_e) {}
  }
  const keys = Array.from(map.keys()).sort()
  return {
    prefixSearch(prefix) {
      const out = []
      let low = 0
      let high = keys.length
      while (low < high) {
        const middle = (low + high) >> 1
        if (keys[middle] < prefix) low = middle + 1
        else high = middle
      }
      for (let index = low; index < keys.length; index += 1) {
        const text = keys[index]
        if (!text.startsWith(prefix)) break
        out.push({ text, info: map.get(text) })
      }
      return out
    },
  }
}

/** @deprecated use nativeEvidenceLookup */
export function nativeFreqLookup(runtime, native) {
  return nativeEvidenceLookup(runtime, native).unigram
}

function loadTextNativeEvidence(load, paths) {
  const unigramMap = new Map()
  const stemMap = new Map()
  const attestedSet = new Set()
  let floor = 50
  let maxUni = 1
  for (const p of paths.unigram) {
    try {
      const raw = load(p)
      if (!raw) continue
      for (const line of String(raw).split('\n')) {
        if (!line) continue
        const parts = line.split('\t')
        if (parts.length >= 2 && /^\d+$/.test(parts[1])) {
          const c = Number(parts[1])
          unigramMap.set(parts[0], c)
          if (c > maxUni) maxUni = c
        }
      }
      break
    } catch (_e) {}
  }
  for (const p of paths.stems) {
    try {
      const raw = load(p)
      if (!raw) continue
      const data = JSON.parse(raw)
      for (const [k, v] of Object.entries(data || {})) stemMap.set(k, Number(v) || 0)
      break
    } catch (_e) {}
  }
  for (const p of paths.attested) {
    try {
      const raw = load(p)
      if (!raw) continue
      const data = JSON.parse(raw)
      const words = data.words || data
      if (Array.isArray(words)) for (const w of words) if (w) attestedSet.add(String(w))
      else for (const w of Object.keys(words || {})) attestedSet.add(w)
      if (Number.isFinite(Number(data.floor))) floor = Number(data.floor)
      break
    } catch (_e) {}
  }
  return { unigramMap, stemMap, attestedSet, floor, maxUni }
}

/**
 * loadRuntimeStorage(env, options)
 * options.allowTextFallback — required for JSON/TSV; never implied by missing Trie.
 * options.releaseMode — if true, missing Trie/bins throws/returns error capability.
 */
export function loadRuntimeStorage(env, options) {
  const opts = options || {}
  const allowText = !!opts.allowTextFallback
  const releaseMode = opts.releaseMode !== false && !allowText
  const load = opts.loadFile || ((p) => (env && env.loadFile ? env.loadFile(p) : ''))
  const paths = assetPaths(env && env.userDataDir)

  const TrieCtor = opts.TrieCtor || hostTrieCtor()
  const capabilities = {
    hostTrie: typeof TrieCtor === 'function',
    writeFileAtomic: !!(env && typeof env.writeFileAtomic === 'function'),
    releaseMode,
    allowTextFallback: allowText,
    error: null,
  }

  if (releaseMode && !capabilities.hostTrie) {
    capabilities.error = 'globalThis.Trie unavailable in release mode'
    console.log('$qjs$ FAIL: ' + capabilities.error)
    return {
      mode: 'error',
      lexicon: { trie: null, map: new Map(), weights: new Map(), exceptions: new Map() },
      prefix: { trie: null },
      nativeLm: { trie: null, map: null, unigramMap: null, stemMap: null, attestedSet: null, maxUni: 1, floor: 50 },
      capabilities,
      policy: null,
    }
  }

  const exceptions = loadExceptions(load, paths.exceptions)
  const policyRaw = loadJson(load, paths.policy)
  const nativeLmMeta = loadJson(load, paths.nativeLmMeta)

  let lexiconTrie = tryLoadNativeTrie(env, 'js/lexicon.trie.bin', true, TrieCtor)
  let prefixTrie = tryLoadNativeTrie(env, 'js/prefix.trie.bin', true, TrieCtor)
  let nativeLmTrie = tryLoadNativeTrie(env, 'js/native_lm.trie.bin', true, TrieCtor)

  const lexiconMap = new Map()
  const weightsMap = new Map()
  const lexiconNativeSet = new Set()
  let mode = 'empty'
  let nativeLm = {
    trie: nativeLmTrie,
    map: null,
    unigramMap: null,
    stemMap: null,
    attestedSet: null,
    maxUni: Math.max(1, Number(nativeLmMeta && nativeLmMeta.max_unigram) || 1),
    floor: Math.max(0, Number(nativeLmMeta && nativeLmMeta.attested_floor) || 50),
    metadata: nativeLmMeta,
  }

  const metaValid =
    nativeLmMeta &&
    Number(nativeLmMeta.version) === 1 &&
    nativeLmMeta.payload_format === 'unigram\\tstem\\tattested' &&
    Number(nativeLmMeta.max_unigram) > 0

  if (lexiconTrie && prefixTrie && nativeLmTrie && metaValid) {
    mode = 'trie'
    console.log('$qjs$ lexicon trie binary loaded')
    console.log('$qjs$ prefix trie binary loaded')
    console.log('$qjs$ native_lm trie binary loaded')
  } else if (allowText) {
    // Explicit development fallback only
    for (const p of paths.lexiconBlob) {
      try {
        const raw = load(p)
        if (!raw) continue
        const blob = JSON.parse(raw)
        for (const [k, v] of Object.entries(blob.exceptions || {})) {
          exceptions.set(String(k).toLowerCase(), v)
        }
        for (const [k, v] of Object.entries(blob.lexicon || {})) {
          const key = String(k).toLowerCase()
          lexiconMap.set(key, v)
          if (v) lexiconNativeSet.add(String(v))
          const w = blob.weights && blob.weights[k] != null ? Number(blob.weights[k]) : 100
          weightsMap.set(key, w)
        }
        mode = 'map'
        console.log('$qjs$ lexicon map fallback entries=' + lexiconMap.size)
        break
      } catch (_e) {}
    }
    const te = loadTextNativeEvidence(load, paths)
    prefixTrie = loadTextPrefixIndex(load, paths.prefixText)
    nativeLm = {
      trie: null,
      map: null,
      unigramMap: te.unigramMap,
      stemMap: te.stemMap,
      attestedSet: te.attestedSet,
      lexiconNativeSet,
      maxUni: te.maxUni,
      floor: te.floor,
      metadata: {
        version: 1,
        payload_format: 'unigram\\tstem\\tattested',
        max_unigram: te.maxUni,
        attested_floor: te.floor,
      },
    }
    console.log('$qjs$ native evidence text fallback uni=' + te.unigramMap.size)
  } else {
    const missing = []
    if (!lexiconTrie) missing.push('lexicon.trie.bin')
    if (!prefixTrie) missing.push('prefix.trie.bin')
    if (!nativeLmTrie) missing.push('native_lm.trie.bin')
    if (!metaValid) missing.push('native_lm_meta.json')
    capabilities.error = 'required binary Tries missing: ' + missing.join(', ')
    console.log('$qjs$ FAIL: ' + capabilities.error)
    mode = 'error'
  }

  const lexicon = {
    trie: lexiconTrie,
    map: lexiconMap,
    weights: weightsMap,
    exceptions,
  }
  const emoji = loadEmojiStorage(load, paths.emoji, lexicon)
  console.log('$qjs$ emoji loaded romans=' + emoji.byRoman.size + ' natives=' + emoji.byNative.size)
  return {
    mode,
    lexicon,
    prefix: { trie: prefixTrie },
    nativeLm,
    emoji,
    policy: policyRaw,
    capabilities,
  }
}

export function loadLexiconStorage(env, loadFileFn) {
  const rt = loadRuntimeStorage(env, { loadFile: loadFileFn, allowTextFallback: true })
  return {
    mode: rt.mode,
    trie: rt.lexicon.trie,
    lexicon: rt.lexicon.map,
    weights: rt.lexicon.weights,
    exceptions: rt.lexicon.exceptions,
  }
}

export function trieFind(runtime, key) {
  if (!key || !runtime) return null
  const k = String(key).toLowerCase()
  const lex = runtime.lexicon || runtime
  if (lex.exceptions && lex.exceptions.has(k)) {
    return { native: lex.exceptions.get(k), weight: 1000, soft: false, exception: true }
  }
  if (lex.trie) {
    try {
      const hit = lex.trie.find(k)
      if (hit == null) return null
      const parts = String(hit).split('\x1f')
      return { native: parts[0], weight: Number(parts[1] || 100), soft: parts[2] === '1' }
    } catch (_e) {
      return null
    }
  }
  if (lex.map && lex.map.has(k)) {
    const w = lex.weights ? Number(lex.weights.get(k) || 100) : 100
    return { native: lex.map.get(k), weight: w, soft: w > 0 && w < 100 }
  }
  return null
}

export function prefixSearch(runtime, key, limit) {
  const lim = limit || 32
  const trie = runtime && runtime.prefix && runtime.prefix.trie
  if (!trie || typeof trie.prefixSearch !== 'function') return []
  try {
    return trie.prefixSearch(String(key).toLowerCase(), lim) || []
  } catch (_e) {
    return []
  }
}

/** Max unigram for score normalization. */
export function nativeLmMax(runtime) {
  if (!runtime || !runtime.nativeLm) return 1
  if (runtime.nativeLm.maxUni) return runtime.nativeLm.maxUni
  return 1
}
