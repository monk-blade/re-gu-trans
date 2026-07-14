/**
 * Storage adapters — prefer native Trie binaries; Maps only as fail-open fallback.
 */
export const STORAGE_VERSION = 2

export function lexiconPaths(userDataDir) {
  const paths = ['js/gu_lexicon_blob.json']
  if (userDataDir) paths.unshift(String(userDataDir).replace(/\/$/, '') + '/js/gu_lexicon_blob.json')
  return paths
}

export function assetPaths(userDataDir) {
  const base = userDataDir ? String(userDataDir).replace(/\/$/, '') : null
  const join = (rel) => (base ? base + '/' + rel : rel)
  return {
    lexiconBin: [join('js/lexicon.trie.bin'), 'js/lexicon.trie.bin'],
    prefixBin: [join('js/prefix.trie.bin'), 'js/prefix.trie.bin'],
    nativeLmBin: [join('js/native_lm.trie.bin'), 'js/native_lm.trie.bin'],
    exceptions: [join('js/exceptions.json'), 'js/exceptions.json'],
    emoji: [join('js/emoji_keywords.json'), 'js/emoji_keywords.json'],
    policy: [join('js/ranking_policy.json'), 'js/ranking_policy.json'],
    // Build-input / legacy fallbacks (not shipped in release payloads)
    lexiconBlob: [join('js/gu_lexicon_blob.json'), 'js/gu_lexicon_blob.json'],
    lexiconTxt: [join('js/lexicon.trie.txt'), 'js/lexicon.trie.txt'],
    unigram: [join('js/lm/unigram.tsv'), 'js/lm/unigram.tsv'],
    stems: [join('js/lm/stems.json'), 'js/lm/stems.json'],
    attested: [join('js/lm/attested.json'), 'js/lm/attested.json'],
  }
}

/** @deprecated use assetPaths */
export function lmPaths(userDataDir) {
  return assetPaths(userDataDir)
}

export function tryLoadNativeTrie(env, relativePath, preferBinary) {
  try {
    if (typeof Trie === 'undefined') return null
    const trie = new Trie()
    const root = env && env.userDataDir ? String(env.userDataDir).replace(/\/$/, '') + '/' : ''
    const abs = root + relativePath
    if (preferBinary !== false && typeof trie.loadBinaryFile === 'function') {
      const bin = abs.endsWith('.bin') ? abs : abs.replace(/\.txt$/, '.bin').replace(/\.tsv$/, '.trie.bin')
      try {
        trie.loadBinaryFile(bin)
        return trie
      } catch (_e) {
        /* fall through to text */
      }
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

/**
 * Load lexicon: prefer lexicon.trie.bin (+ exceptions.json). Return
 * { mode:'trie'|'map', trie, lexicon:Map, weights:Map, exceptions:Map }.
 */
export function loadLexiconStorage(env, loadFileFn) {
  const load = loadFileFn || ((p) => (env && env.loadFile ? env.loadFile(p) : ''))
  const paths = assetPaths(env && env.userDataDir)
  const exceptions = new Map()
  for (const p of paths.exceptions) {
    try {
      const raw = load(p)
      if (!raw) continue
      const data = JSON.parse(raw)
      const ex = data.exceptions || data
      for (const [k, v] of Object.entries(ex)) exceptions.set(String(k).toLowerCase(), v)
      break
    } catch (_e) {}
  }

  const trie = tryLoadNativeTrie(env, 'js/lexicon.trie.bin', true)
  if (trie) {
    console.log('$qjs$ lexicon trie binary loaded')
    return { mode: 'trie', trie, lexicon: null, weights: null, exceptions }
  }

  // Fail-open: JSON blob Maps (dev / missing bins)
  const lexicon = new Map()
  const weights = new Map()
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
        lexicon.set(key, v)
        const w = blob.weights && blob.weights[k] != null ? Number(blob.weights[k]) : 100
        weights.set(key, w)
      }
      console.log('$qjs$ lexicon map fallback entries=' + lexicon.size)
      return { mode: 'map', trie: null, lexicon, weights, exceptions }
    } catch (_e) {}
  }
  return { mode: 'empty', trie: null, lexicon, weights, exceptions }
}

export function trieFind(storage, key) {
  if (!key) return null
  const k = String(key).toLowerCase()
  if (storage.mode === 'trie' && storage.trie) {
    try {
      const hit = storage.trie.find(k)
      if (hit == null) return null
      // payload: native\\x1fweight\\x1fsoft
      const parts = String(hit).split('\x1f')
      return { native: parts[0], weight: Number(parts[1] || 100), soft: parts[2] === '1' }
    } catch (_e) {
      return null
    }
  }
  if (storage.lexicon && storage.lexicon.has(k)) {
    return {
      native: storage.lexicon.get(k),
      weight: storage.weights ? Number(storage.weights.get(k) || 100) : 100,
      soft: false,
    }
  }
  return null
}
