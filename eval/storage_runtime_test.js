import {
  loadRuntimeStorage,
  nativeEvidenceLookup,
  parseNativeLmPayload,
  trieFind,
} from '../rime/js/storage.js'

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(message + ': expected=' + expected + ' actual=' + actual)
}

const binaryMaps = {
  'lexicon.trie.bin': new Map([['padi', 'પડી\x1f800\x1f0']]),
  'prefix.trie.bin': new Map([['pa', 'પડી\x1f800\x1fpadi']]),
  'native_lm.trie.bin': new Map([['પડી', '42\t7\t1']]),
}

class FakeTrie {
  loadBinaryFile(path) {
    const name = String(path).split('/').pop()
    const source = binaryMaps[name]
    if (!source) throw new Error('missing fake binary ' + name)
    this.map = source
  }
  find(key) {
    return this.map.has(key) ? this.map.get(key) : null
  }
  prefixSearch(prefix) {
    const rows = []
    for (const [key, info] of this.map.entries()) {
      if (key.startsWith(prefix)) rows.push({ text: key, info })
    }
    return rows
  }
}

const files = {
  '/mock/js/native_lm_meta.json': JSON.stringify({
    version: 1,
    payload_format: 'unigram\\tstem\\tattested',
    max_unigram: 100,
    attested_floor: 60,
  }),
  '/mock/js/exceptions.json': '{"exceptions":{}}',
  '/mock/js/ranking_policy.json': '{"version":2}',
}
const env = {
  userDataDir: '/mock',
  loadFile(path) { return files[path] || '' },
}

const runtime = loadRuntimeStorage(env, { TrieCtor: FakeTrie, releaseMode: true })
assertEqual(runtime.mode, 'trie', 'fake binary runtime')
assertEqual(runtime.nativeLm.maxUni, 100, 'metadata max')
assertEqual(runtime.nativeLm.floor, 60, 'metadata floor')
assertEqual(trieFind(runtime, 'padi').native, 'પડી', 'binary lexicon lookup')
const evidence = nativeEvidenceLookup(runtime, 'પડી')
assertEqual(evidence.unigram, 42, 'binary unigram')
assertEqual(evidence.stem, 7, 'binary stem')
assertEqual(evidence.attested, true, 'binary attested')
assertEqual(parseNativeLmPayload('12\t5\t0').attested, false, 'payload false flag')

const missingMeta = loadRuntimeStorage(
  { userDataDir: '/bad', loadFile() { return '' } },
  { TrieCtor: FakeTrie, releaseMode: true }
)
assertEqual(missingMeta.mode, 'error', 'release rejects missing metadata')
assert(String(missingMeta.capabilities.error).includes('native_lm_meta.json'), 'metadata error named')

console.log(JSON.stringify({ ok: true, injected_trie: true, finite_evidence: true }))
