/**
 * Storage adapters — lexicon / LM / optional native Trie.
 * Loaded by gujarati_translator.js (and by eval via ranking_policy).
 */
export const STORAGE_VERSION = 1

export function lexiconPaths(userDataDir) {
  const paths = ['js/gu_lexicon_blob.json']
  if (userDataDir) paths.unshift(String(userDataDir).replace(/\/$/, '') + '/js/gu_lexicon_blob.json')
  return paths
}

export function lmPaths(userDataDir) {
  const base = userDataDir ? String(userDataDir).replace(/\/$/, '') : null
  return {
    unigram: [base ? base + '/js/lm/unigram.tsv' : null, 'js/lm/unigram.tsv'].filter(Boolean),
    stems: [base ? base + '/js/lm/stems.json' : null, 'js/lm/stems.json'].filter(Boolean),
    attested: [base ? base + '/js/lm/attested.json' : null, 'js/lm/attested.json'].filter(Boolean),
    policy: [base ? base + '/js/ranking_policy.json' : null, 'js/ranking_policy.json'].filter(Boolean),
    lexiconTrie: [base ? base + '/js/lexicon.trie.txt' : null, 'js/lexicon.trie.txt'].filter(Boolean),
    prefixTrie: [base ? base + '/js/prefix.trie.txt' : null, 'js/prefix.trie.txt'].filter(Boolean),
    nativeLm: [base ? base + '/js/native_lm.tsv' : null, 'js/native_lm.tsv'].filter(Boolean),
  }
}

/**
 * Prefer qjs native Trie when available; otherwise null (caller uses Map).
 * @param {Environment} env
 * @param {string} relativePath
 */
export function tryLoadNativeTrie(env, relativePath) {
  try {
    if (typeof Trie === 'undefined') return null
    const trie = new Trie()
    const abs = env && env.userDataDir
      ? String(env.userDataDir).replace(/\/$/, '') + '/' + relativePath
      : relativePath
    if (typeof trie.loadTextFile === 'function') {
      trie.loadTextFile(abs)
      return trie
    }
    if (typeof trie.loadBinaryFile === 'function') {
      const bin = abs.replace(/\.txt$/, '.bin')
      trie.loadBinaryFile(bin)
      return trie
    }
  } catch (e) {
    console.log('$qjs$ trie load skipped: ' + (e && e.message))
  }
  return null
}
