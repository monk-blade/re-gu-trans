// gujarati_translator.js
// Thin Rime adapter over js/{ranking,phonetic,storage,learning}.js (+ inlined generators).

import {
  lexiconHitTier as modLexiconHitTier,
  layoutMenu,
  makeCandidateRecord,
  loadPolicyFromText,
  onsetOnlyLongAPenalty,
  applyLinearCoefficients,
} from './ranking.js'
import { expandRomanLattice, filterLatticeNatives } from './phonetic.js'
import { loadLexiconStorage, trieFind, assetPaths } from './storage.js'
import {
  LEARNING_FILE,
  persistLearningAtomic,
  recordChoice as learningRecordChoice,
  parseLearning,
  emptyLearning,
  choiceCount,
} from './learning.js'

void modLexiconHitTier
void layoutMenu
void makeCandidateRecord
void loadPolicyFromText
void onsetOnlyLongAPenalty
void applyLinearCoefficients
void expandRomanLattice
void filterLatticeNatives
void loadLexiconStorage
void trieFind
void assetPaths
void LEARNING_FILE
void persistLearningAtomic
void learningRecordChoice
void parseLearning
void emptyLearning
void choiceCount

// Gujarati phonetic transliteration engine for Rime using librime-qjs
//
// Transliteration scheme (IAST-inspired, phonetic):
//   Vowels: a અ, aa આ, i ઇ, ee/ii ઈ, u ઉ, oo/uu ઊ, R ઋ, RR ૠ, E ઍ, e એ, ai ઐ,
//            O ઑ, o ઓ, au ઔ, aM અં, aH અઃ, oM ઓં
//   Consonants: k ક, kh ખ, g ગ, gh ઘ, ng ઙ,
//               c/ch ચ, chh છ, j જ, jh ઝ, ny ઞ,
//               T ટ, Th ઠ, D ડ, Dh ઢ, N ણ,
//               t ત, th થ, d દ, dh ધ, n ન,
//               p પ, ph/f ફ, b બ, bh ભ, m મ,
//               y ય, r ર, l લ, L ળ, v/w વ,
//               sh શ, Sh ષ, s સ, h હ,
//               x/ksh ક્ષ, gy જ્ઞ, dv દ્વ, z ઝ
//   Digits: 0 ૦, 1 ૧, 2 ૨, 3 ૩, 4 ૪, 5 ૫, 6 ૬, 7 ૭, 8 ૮, 9 ૯
//   Virama (halant): + forces explicit halant on preceding consonant
//
// Behavior:
//   - Consonant alone carries implicit short 'a'
//   - Consonant + vowel = consonant with corresponding matra
//   - Consonant followed by another consonant = first gets virama (્)
//   - '+' forces virama explicitly
//   - Arabic digits transliterate to Gujarati digits
//   - Unknown characters pass through unchanged (punctuation, spaces)
//   - Dictionary lookup for common Gujarati words (trie-backed for speed)

const VIRAMA = '\u0ACD'

// ---------------------------------------------------------------------------
// Gujarati digits
// ---------------------------------------------------------------------------

const DIGITS = {
  '0': '\u0AE6', // ૦
  '1': '\u0AE7', // ૧
  '2': '\u0AE8', // ૨
  '3': '\u0AE9', // ૩
  '4': '\u0AEA', // ૪
  '5': '\u0AEB', // ૫
  '6': '\u0AEC', // ૬
  '7': '\u0AED', // ૭
  '8': '\u0AEE', // ૮
  '9': '\u0AEF', // ૯
}

// ---------------------------------------------------------------------------
// Vowel mappings
// ---------------------------------------------------------------------------

const VOWEL_INDEPENDENT = {
  'a':  '\u0A85', // અ
  'aa': '\u0A86', // આ
  'i':  '\u0A87', // ઇ
  'ee': '\u0A88', // ઈ
  'ii': '\u0A88', // ઈ
  'u':  '\u0A89', // ઉ
  'oo': '\u0A8A', // ઊ
  'uu': '\u0A8A', // ઊ
  'R':  '\u0A8B', // ઋ
  'RR': '\u0AE0', // ૠ
  'E':  '\u0A8D', // ઍ
  'e':  '\u0A8F', // એ
  'ai': '\u0A90', // ઐ
  'O':  '\u0A91', // ઑ
  'o':  '\u0A93', // ઓ
  'au': '\u0A94', // ઔ
  'M':  '\u0A82', // ં  (anusvara)
  'H':  '\u0A83', // ઃ  (visarga)
}

const VOWEL_MATRAS = {
  'aa': '\u0ABE', // ા
  'i':  '\u0ABF', // િ
  'ee': '\u0AC0', // ી
  'ii': '\u0AC0', // ી
  'u':  '\u0AC1', // ુ
  'oo': '\u0AC2', // ૂ
  'uu': '\u0AC2', // ૂ
  'R':  '\u0AC3', // ૃ
  'RR': '\u0AC4', // ૄ
  'E':  '\u0AC5', // ૅ
  'e':  '\u0AC7', // ે
  'ai': '\u0AC8', // ૈ
  'O':  '\u0AC9', // ૉ
  'o':  '\u0ACB', // ો
  'au': '\u0ACC', // ૌ
  'M':  '\u0A82', // ં
  'H':  '\u0A83', // ઃ
}

// ---------------------------------------------------------------------------
// Consonant mappings
// ---------------------------------------------------------------------------

const CONSONANTS = {
  'k':   '\u0A95', // ક
  'kh':  '\u0A96', // ખ
  'g':   '\u0A97', // ગ
  'gh':  '\u0A98', // ઘ
  'ng':  '\u0A99', // ઙ
  'c':   '\u0A9A', // ચ
  'ch':  '\u0A9A', // ચ
  'chh': '\u0A9B', // છ
  'j':   '\u0A9C', // જ
  'jh':  '\u0A9D', // ઝ
  'ny':  '\u0A9E', // ઞ
  'T':   '\u0A9F', // ટ
  'Th':  '\u0AA0', // ઠ
  'D':   '\u0AA1', // ડ
  'Dh':  '\u0AA2', // ઢ
  'N':   '\u0AA3', // ણ
  't':   '\u0AA4', // ત
  'th':  '\u0AA5', // થ
  'd':   '\u0AA6', // દ
  'dh':  '\u0AA7', // ધ
  'n':   '\u0AA8', // ન
  'p':   '\u0AAA', // પ
  'ph':  '\u0AAB', // ફ
  'f':   '\u0AAB', // ફ
  'b':   '\u0AAC', // બ
  'bh':  '\u0AAD', // ભ
  'm':   '\u0AAE', // મ
  'y':   '\u0AAF', // ય
  'r':   '\u0AB0', // ર
  'l':   '\u0AB2', // લ
  'L':   '\u0AB3', // ળ
  'v':   '\u0AB5', // વ
  'w':   '\u0AB5', // વ
  'sh':  '\u0AB6', // શ
  'Sh':  '\u0AB7', // ષ
  's':   '\u0AB8', // સ
  'h':   '\u0AB9', // હ
  'x':   '\u0A95\u0ACD\u0AB7', // ક્ષ
  'ksh': '\u0A95\u0ACD\u0AB7', // ક્ષ
  'gy':  '\u0A9C\u0ACD\u0A9E', // જ્ઞ
  'gn':  '\u0A9C\u0ACD\u0A9E', // જ્ઞ (gnan)
  'gny': '\u0A9C\u0ACD\u0A9E', // જ્ઞ
  'jny': '\u0A9C\u0ACD\u0A9E', // જ્ઞ
  'dv':  '\u0AA6\u0ACD\u0AB5', // દ્વ
  'shr': '\u0AB6\u0ACD\u0AB0', // શ્ર
  'tr':  '\u0AA4\u0ACD\u0AB0', // ત્ર
  'sth': '\u0AB8\u0ACD\u0AA5', // સ્થ
  'str': '\u0AB8\u0ACD\u0AA4\u0ACD\u0AB0', // સ્ત્ર
  'z':   '\u0A9D', // ઝ
  'om':  '\u0AD0', // ૐ
}

// ---------------------------------------------------------------------------
// Common Gujarati words dictionary
// Maps transliteration (lowercase) → Gujarati
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Apple gu-Mappings preferred overlays (distilled)
// First listed glyph is preferred when generating phonetic candidates.
// ---------------------------------------------------------------------------
const APPLE_PREFERRED = {
  'aai': 'આઈ',
  'aao': 'આઓ',
  'chh': 'છ',
  'iaa': 'ઇઆ',
  'ksh': 'ક્ષ',
  'oie': 'ોઇએ',
  'shr': 'શ્ર',
  'thh': 'ઠ',
  'aa': 'આ',
  'ae': 'એ',
  'ai': 'ઐ',
  'ao': 'આઓ',
  'au': 'ઔ',
  'bh': 'ભ',
  'ch': 'ચ',
  'dh': 'ધ',
  'ee': 'ઈ',
  'gh': 'ઘ',
  'gy': 'જ્ઞ',
  'ia': 'િયા',
  'io': 'ઇઓ',
  'jh': 'ઝ',
  'kh': 'ખ',
  'oe': 'ઓએ',
  'oi': 'ઓઇ',
  'oo': 'ઉ',
  'ph': 'ફ',
  'ra': 'ૃ',
  'rh': 'ઢ',
  'ri': 'ઋ',
  'ru': 'ઋ',
  'sh': 'શ',
  'th': 'થ',
  'tr': 'ત્ર',
  'uo': 'ુઓ',
  'a': 'અ',
  'b': 'બ',
  'c': 'ક',
  'd': 'દ',
  'e': 'એ',
  'f': 'ફ',
  'g': 'ગ',
  'h': 'હ',
  'i': 'ઇ',
  'j': 'જ',
  'k': 'ક',
  'l': 'લ',
  'm': 'મ',
  'n': 'ન',
  'o': 'ઓ',
  'p': 'પ',
  'r': 'ર',
  's': 'સ',
  't': 'ટ',
  'u': 'ઉ',
  'v': 'વ',
  'w': 'વ',
  'x': 'ક્ષ',
  'y': 'ય',
  'z': 'ઝ',
}

// WORD_DICT removed — generated lexicon covers these entries.

// ---------------------------------------------------------------------------
// Trie for fast prefix matching
// ---------------------------------------------------------------------------

class TrieNode {
  constructor() {
    this.children = new Map()
    this.value = null
  }
}

class Trie {
  constructor() {
    this.root = new TrieNode()
  }

  insert(key, value) {
    let node = this.root
    for (const char of key) {
      if (!node.children.has(char)) {
        node.children.set(char, new TrieNode())
      }
      node = node.children.get(char)
    }
    node.value = value
  }

  findExact(key) {
    let node = this.root
    for (const char of key) {
      if (!node.children.has(char)) return null
      node = node.children.get(char)
    }
    return node.value
  }

  findPrefixMatches(prefix, limit = 20) {
    return this.findPrefixEntries(prefix, limit).map((e) => e.value)
  }

  // Returns { key, value } for roman keys under prefix (includes exact key if present).
  findPrefixEntries(prefix, limit = 20) {
    let node = this.root
    for (const char of prefix) {
      if (!node.children.has(char)) return []
      node = node.children.get(char)
    }
    const matches = []
    this._collectEntries(node, prefix, matches, limit)
    return matches
  }

  _collectEntries(node, keySoFar, matches, limit) {
    if (matches.length >= limit) return
    if (node.value !== null) {
      matches.push({ key: keySoFar, value: node.value })
    }
    for (const [ch, child] of node.children.entries()) {
      this._collectEntries(child, keySoFar + ch, matches, limit)
      if (matches.length >= limit) return
    }
  }
}

const DICT_TRIE = new Trie()

// ---------------------------------------------------------------------------
// Distilled Apple lexicon / exceptions (loaded from JSON blob)
// ---------------------------------------------------------------------------

const LEXICON_BLOB_PATHS = [
  'js/gu_lexicon_blob.json',
  '~/Library/Rime/js/gu_lexicon_blob.json',
]

let APPLE_EXCEPTIONS = new Map()
let APPLE_LEXICON = new Map()
let APPLE_WEIGHTS = new Map() // roman → corpus/Apple weight (general ranking)
let KNOWN_WORDS = new Set()
let LEXICON_LOADED = false
let NATIVE_LEX_TRIE = null
let NATIVE_PFX_TRIE = null

// Candidate tiers — primary sort key (lower = better).
const TIER_PERSONALIZED = -1 // user learning (≥threshold) — above default exact
const TIER_EXACT = 0
const TIER_DICT = 1   // phonetic form attested via native wordlist / stem (macOS-like)
const TIER_PHONETIC = 2
const TIER_LATIN = 3  // echo latin below script phonetics (Google/Apple-like)
const TIER_PREFIX = 4
const TIER_EMOJI = 5  // keyword emoji; always below script candidates
const TIER_MAX = 5

function rememberKnownWord(word) {
  if (word) KNOWN_WORDS.add(word)
}

function parseLexPayload(raw) {
  if (raw == null || raw === '') return null
  const parts = String(raw).split('\x1f')
  return {
    native: parts[0],
    weight: Number(parts[1] || 100) || 100,
    soft: parts[2] === '1',
  }
}

function nativeLexHit(roman) {
  if (!NATIVE_LEX_TRIE || !roman) return null
  try {
    const raw = NATIVE_LEX_TRIE.find(String(roman).toLowerCase())
    return parseLexPayload(raw)
  } catch (_e) {
    return null
  }
}

function lexiconWeight(roman) {
  if (!roman) return 0
  const hit = nativeLexHit(roman)
  if (hit) return hit.weight
  return APPLE_WEIGHTS.get(String(roman).toLowerCase()) || 0
}

function loadTextViaEnv(env, absolutePath) {
  if (!absolutePath) return null
  if (env && typeof env.loadFile === 'function') {
    try {
      const text = env.loadFile(absolutePath)
      if (text) return text
    } catch (e) {
      // try next path
    }
  }
  if (env && typeof env.fileExists === 'function') {
    try {
      if (!env.fileExists(absolutePath)) return null
    } catch (e) {
      return null
    }
  }
  return readFileText(absolutePath)
}

function loadExceptionsJson(env) {
  const paths = []
  if (env && env.userDataDir) paths.push(env.userDataDir + '/js/exceptions.json')
  paths.push(resolveUserPath('js/exceptions.json'))
  for (const p of paths) {
    const text = loadTextViaEnv(env, p)
    if (!text) continue
    try {
      const data = JSON.parse(text)
      const ex = data.exceptions || data
      for (const [k, v] of Object.entries(ex)) {
        const word = typeof v === 'string' ? v : (v && v.text) || ''
        if (!word) continue
        APPLE_EXCEPTIONS.set(String(k).toLowerCase(), word)
        rememberKnownWord(word)
      }
      return true
    } catch (_e) {}
  }
  return false
}

function installNativeLexFacades() {
  APPLE_LEXICON = {
    get(k) {
      const hit = nativeLexHit(k)
      return hit ? hit.native : undefined
    },
    has(k) {
      return !!nativeLexHit(k)
    },
    set(_k, _v) {},
    get size() {
      return -1
    },
  }
  APPLE_WEIGHTS = {
    get(k) {
      const hit = nativeLexHit(k)
      return hit ? hit.weight : 0
    },
    set(_k, _v) {},
    has(k) {
      return !!nativeLexHit(k)
    },
  }
  DICT_TRIE.findExact = function findExactNative(key) {
    const hit = nativeLexHit(key)
    return hit ? hit.native : null
  }
  DICT_TRIE.findPrefixEntries = function findPrefixNative(prefix, limit = 20) {
    if (!NATIVE_PFX_TRIE || !prefix) return []
    try {
      const rows = NATIVE_PFX_TRIE.prefixSearch(String(prefix).toLowerCase()) || []
      const out = []
      for (const row of rows) {
        const key = row.text || row.key || ''
        const info = row.info || row.value || ''
        const first = String(info).split('\x1e')[0]
        const parts = first.split('\x1f')
        const native = parts[0]
        if (!native) continue
        out.push({ key: key || prefix, value: native })
        if (out.length >= limit) break
      }
      return out
    } catch (_e) {
      return []
    }
  }
}

function loadLexiconBlob(env) {
  if (LEXICON_LOADED) return
  LEXICON_LOADED = true
  loadExceptionsJson(env)

  try {
    if (typeof Trie !== 'undefined') {
      const root = env && env.userDataDir ? String(env.userDataDir).replace(/\/$/, '') + '/' : ''
      const trie = new Trie()
      trie.loadBinaryFile(root + 'js/lexicon.trie.bin')
      NATIVE_LEX_TRIE = trie
      try {
        const pfx = new Trie()
        pfx.loadBinaryFile(root + 'js/prefix.trie.bin')
        NATIVE_PFX_TRIE = pfx
      } catch (_e) {
        NATIVE_PFX_TRIE = null
      }
      installNativeLexFacades()
      console.log('$qjs$ lexicon trie binary loaded')
      return
    }
  } catch (e) {
    console.log('$qjs$ lexicon binary skipped: ' + (e && e.message))
    NATIVE_LEX_TRIE = null
  }

  const paths = []
  if (env && env.userDataDir) {
    paths.push(env.userDataDir + '/js/gu_lexicon_blob.json')
  }
  for (const p of LEXICON_BLOB_PATHS) {
    paths.push(resolveUserPath(p))
  }

  let text = null
  let used = null
  for (const p of paths) {
    text = loadTextViaEnv(env, p)
    if (text) {
      used = p
      break
    }
  }
  if (!text) {
    console.log('$qjs$ lexicon blob missing; phonetic/Latin fallback only')
    return
  }
  try {
    const data = JSON.parse(text)
    if (data.exceptions) {
      for (const [k, v] of Object.entries(data.exceptions)) {
        const word = typeof v === 'string' ? v : (v && v.text) || ''
        if (!word) continue
        APPLE_EXCEPTIONS.set(String(k).toLowerCase(), word)
        DICT_TRIE.insert(String(k).toLowerCase(), word)
        rememberKnownWord(word)
        APPLE_WEIGHTS.set(String(k).toLowerCase(), 1000)
      }
    }
    if (data.weights) {
      for (const [k, w] of Object.entries(data.weights)) {
        const n = Number(w)
        if (Number.isFinite(n)) APPLE_WEIGHTS.set(String(k).toLowerCase(), n)
      }
    }
    if (data.lexicon) {
      let n = 0
      for (const [k, v] of Object.entries(data.lexicon)) {
        const key = String(k).toLowerCase()
        const word = typeof v === 'string' ? v : (v && v.text) || ''
        if (!word) continue
        APPLE_LEXICON.set(key, word)
        rememberKnownWord(word)
        if (!DICT_TRIE.findExact(key)) {
          DICT_TRIE.insert(key, word)
        }
        if (!APPLE_WEIGHTS.has(key) && v && typeof v === 'object' && Number.isFinite(Number(v.weight))) {
          APPLE_WEIGHTS.set(key, Number(v.weight))
        }
        n += 1
      }
      console.log(
        '$qjs$ lexicon map fallback entries=' + n +
        ' weights=' + APPLE_WEIGHTS.size +
        ' exceptions=' + APPLE_EXCEPTIONS.size +
        ' from=' + used
      )
    }
  } catch (e) {
    console.error('$qjs$ lexicon parse error:', e.message)
  }
}



// ---------------------------------------------------------------------------
// Language model and personalization
// ---------------------------------------------------------------------------

const USER_LM_DEFAULT_PATH = '~/Library/Rime/gujarati.user.tsv'
const UNIGRAM_PATH = 'js/lm/unigram.tsv'
const BIGRAM_PATH = 'js/lm/bigram.tsv'
const TRIGRAM_PATH = 'js/lm/trigram.tsv'
const LM_WEIGHTS = {
  unigram: 0.6,
  bigram: 0.9,
  user: 0.6,
}
let TRIGRAM_WEIGHT = 1.1
const CORE_BIGRAMS = new Map([
  ['મારું|નામ', 1200],
  ['હું|નામ', 900],
  ['ગુજરાતી|ભાષા', 800],
])
const USER_FLUSH_THRESHOLD = 8
const SCORE_CACHE_LIMIT = 500

function resolveUserPath(path) {
  if (!path || typeof path !== 'string') return path
  if (path.startsWith('~/') && typeof os !== 'undefined' && os.homedir) {
    return os.homedir() + path.slice(1)
  }
  return path
}

function readFileText(path) {
  if (typeof read !== 'function') return null
  try {
    return read(path)
  } catch (e) {
    return null
  }
}

function readFileTextFromPaths(paths) {
  for (const path of paths) {
    const text = readFileText(path)
    if (text) return text
  }
  return null
}

function loadUnigramLM(paths) {
  const text = readFileTextFromPaths(paths)
  const map = new Map()
  let max = 1
  if (!text) return { map, max }
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    if (!line) continue
    const parts = line.split('\t')
    if (parts.length < 2) continue
    const word = parts[0]
    const count = Number(parts[1])
    if (!word || !Number.isFinite(count)) continue
    map.set(word, count)
    if (count > max) max = count
  }
  return { map, max }
}

function loadBigramLM(paths) {
  const text = readFileTextFromPaths(paths)
  const map = new Map()
  let max = 1
  if (!text) return { map, max }
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    if (!line) continue
    const parts = line.split('\t')
    if (parts.length < 3) continue
    const prev = parts[0]
    const word = parts[1]
    const count = Number(parts[2])
    if (!prev || !word || !Number.isFinite(count)) continue
    map.set(prev + '|' + word, count)
    if (count > max) max = count
  }
  for (const [key, count] of CORE_BIGRAMS.entries()) {
    const existing = map.get(key) || 0
    const next = Math.max(existing, count)
    map.set(key, next)
    if (next > max) max = next
  }
  return { map, max }
}

function loadTrigramLM(paths) {
  const text = readFileTextFromPaths(paths)
  const map = new Map()
  let max = 1
  if (!text) return { map, max }
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    if (!line) continue
    const parts = line.split('\t')
    if (parts.length < 4) continue
    const prev2 = parts[0]
    const prev1 = parts[1]
    const word = parts[2]
    const count = Number(parts[3])
    if (!prev2 || !prev1 || !word || !Number.isFinite(count)) continue
    map.set(prev2 + '|' + prev1 + '|' + word, count)
    if (count > max) max = count
  }
  return { map, max }
}

function loadUserLM(path) {
  const text = readFileText(path)
  const wordCounts = new Map()
  const bigramCounts = new Map()
  const romanChoices = new Map()
  if (!text) return { wordCounts, bigramCounts, romanChoices }
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    if (!line) continue
    const parts = line.split('\t')
    if (parts.length === 2) {
      const word = parts[0]
      const count = Number(parts[1])
      if (!word || !Number.isFinite(count)) continue
      wordCounts.set(word, count)
    } else if (parts.length >= 4 && parts[0] === '@') {
      const roman = String(parts[1] || '').toLowerCase()
      const native = parts[2]
      const count = Number(parts[3])
      if (!roman || !native || !Number.isFinite(count)) continue
      if (!romanChoices.has(roman)) romanChoices.set(roman, new Map())
      romanChoices.get(roman).set(native, count)
    } else if (parts.length >= 3) {
      const prev = parts[0]
      const word = parts[1]
      const count = Number(parts[2])
      if (!prev || !word || !Number.isFinite(count) || prev === '@') continue
      bigramCounts.set(prev + '|' + word, count)
    }
  }
  return { wordCounts, bigramCounts, romanChoices }
}

function writeUserLM(path, wordCounts, bigramCounts, romanChoices) {
  if (typeof write !== 'function') return false
  const lines = []
  for (const [word, count] of wordCounts.entries()) {
    lines.push(word + '\t' + count)
  }
  for (const [key, count] of bigramCounts.entries()) {
    const [prev, word] = key.split('|')
    lines.push(prev + '\t' + word + '\t' + count)
  }
  if (romanChoices) {
    for (const [roman, nest] of romanChoices.entries()) {
      for (const [native, count] of nest.entries()) {
        lines.push('@\t' + roman + '\t' + native + '\t' + count)
      }
    }
  }
  const content = lines.join('\n') + '\n'
  try {
    write(path, content)
    return true
  } catch (e) {
    return false
  }
}

let UNIGRAM_LM = { map: new Map(), max: 1 }
let BIGRAM_LM = { map: new Map(), max: 1 }
let TRIGRAM_LM = { map: new Map(), max: 1 }
let STEM_FREQ = new Map()
let LM_LOADED = false
let USER_LM_PATH = resolveUserPath(USER_LM_DEFAULT_PATH)
let USER_LM = loadUserLM(USER_LM_PATH)
let USER_LM_DIRTY = false
let USER_LM_PENDING_WRITES = 0
const SCORE_CACHE = new Map()

// Keep in sync with scripts/build_gu_word_freq.py SUFFIXES
const GU_SUFFIXES = [
  'વાળાઓ', 'વાળીઓ', 'વાળું', 'વાળી', 'વાળા', 'વાળો',
  'ીઓ', 'ાઓ', 'ોને', 'ાને', 'ીને', 'ુંને',
  'માંથી', 'માં', 'થી', 'ની', 'નો', 'ના', 'ને', 'નું', 'નાં',
  'શે', 'શો', 'શું', 'ીશ', 'ીશું',
  '્યો', '્યા', '્યું',
  'તો', 'તા', 'તી', 'તું', 'તાં',
  'વું', 'વા', 'વાનું', 'વાની', 'વાના',
  'ે', 'ો', 'ા', 'ી', 'ું', 'ાં',
]

const ATTESTED = new Set()
let ATTESTED_FLOOR = 50

// roman keyword / native GU word → [{e, w}, ...]
const EMOJI_BY_ROMAN = new Map()
const EMOJI_BY_NATIVE = new Map()
let EMOJI_LOADED = false

function rememberEmoji(map, key, emoji, weight) {
  if (!key || !emoji) return
  let list = map.get(key)
  if (!list) {
    list = []
    map.set(key, list)
  }
  for (const it of list) {
    if (it.e === emoji) {
      if (weight > it.w) it.w = weight
      return
    }
  }
  list.push({ e: emoji, w: weight })
  list.sort((a, b) => b.w - a.w)
}

function loadEmojiKeywords(env) {
  if (EMOJI_LOADED) return
  EMOJI_LOADED = true
  const paths = []
  if (env && env.userDataDir) {
    paths.push(env.userDataDir + '/js/emoji_keywords.json')
    paths.push(env.userDataDir + '/emoji_keywords.json')
  }
  paths.push(resolveUserPath('~/Library/Rime/js/emoji_keywords.json'))
  paths.push(resolveUserPath('~/Library/Rime/emoji_keywords.json'))

  let text = null
  for (const p of paths) {
    text = loadTextViaEnv(env, p)
    if (text) break
  }
  if (!text) {
    console.log('$qjs$ emoji keywords missing')
    return
  }
  try {
    const data = JSON.parse(text)
    EMOJI_BY_ROMAN.clear()
    EMOJI_BY_NATIVE.clear()
    for (const [code, items] of Object.entries(data || {})) {
      const roman = String(code || '').toLowerCase()
      if (!roman || !Array.isArray(items)) continue
      for (const it of items) {
        const emoji = it && (it.e || it.emoji || it[0])
        const weight = Number((it && (it.w || it.weight || it[1])) || 100)
        if (!emoji) continue
        rememberEmoji(EMOJI_BY_ROMAN, roman, String(emoji), Number.isFinite(weight) ? weight : 100)
        // Reverse-index via Apple lexicon so native candidates also surface emoji
        const native = APPLE_LEXICON.get(roman)
        if (native) {
          rememberEmoji(EMOJI_BY_NATIVE, native, String(emoji), Number.isFinite(weight) ? weight : 100)
        }
      }
    }
    console.log(
      '$qjs$ emoji loaded romans=' + EMOJI_BY_ROMAN.size + ' natives=' + EMOJI_BY_NATIVE.size
    )
  } catch (e) {
    console.error('$qjs$ emoji parse error:', e.message)
  }
}

function loadLanguageModels(env) {
  if (LM_LOADED) return
  LM_LOADED = true
  const uniPaths = []
  const stemPaths = []
  const attestedPaths = []
  if (env && env.userDataDir) {
    uniPaths.push(env.userDataDir + '/js/lm/unigram.tsv')
    uniPaths.push(env.userDataDir + '/lm/unigram.tsv')
    stemPaths.push(env.userDataDir + '/js/lm/stems.json')
    stemPaths.push(env.userDataDir + '/lm/stems.json')
    attestedPaths.push(env.userDataDir + '/js/lm/attested.json')
    attestedPaths.push(env.userDataDir + '/lm/attested.json')
  }
  uniPaths.push(resolveUserPath('~/Library/Rime/js/lm/unigram.tsv'))
  uniPaths.push(resolveUserPath('~/Library/Rime/lm/unigram.tsv'))
  stemPaths.push(resolveUserPath('~/Library/Rime/js/lm/stems.json'))
  attestedPaths.push(resolveUserPath('~/Library/Rime/js/lm/attested.json'))
  attestedPaths.push(resolveUserPath('~/Library/Rime/lm/attested.json'))

  let uniText = null
  for (const p of uniPaths) {
    uniText = loadTextViaEnv(env, p)
    if (uniText) break
  }
  if (uniText) {
    UNIGRAM_LM = loadUnigramLMFromText(uniText)
    console.log('$qjs$ unigram loaded entries=' + UNIGRAM_LM.map.size + ' max=' + UNIGRAM_LM.max)
  } else {
    console.log('$qjs$ unigram missing')
  }

  BIGRAM_LM = loadBigramLM([BIGRAM_PATH, 'lm/bigram.tsv'])
  TRIGRAM_LM = loadTrigramLM([TRIGRAM_PATH, 'lm/trigram.tsv'])

  let stemText = null
  for (const p of stemPaths) {
    stemText = loadTextViaEnv(env, p)
    if (stemText) break
  }
  if (stemText) {
    try {
      const data = JSON.parse(stemText)
      for (const [k, v] of Object.entries(data)) {
        const n = Number(v)
        if (k && Number.isFinite(n)) STEM_FREQ.set(k, n)
      }
      console.log('$qjs$ stems loaded entries=' + STEM_FREQ.size)
    } catch (e) {
      console.error('$qjs$ stems parse error:', e.message)
    }
  }

  let attestedText = null
  for (const p of attestedPaths) {
    attestedText = loadTextViaEnv(env, p)
    if (attestedText) break
  }
  if (attestedText) {
    try {
      const data = JSON.parse(attestedText)
      ATTESTED.clear()
      const words = data.words || data || []
      if (Array.isArray(words)) {
        for (const w of words) {
          if (w) ATTESTED.add(String(w))
        }
      } else if (words && typeof words === 'object') {
        for (const w of Object.keys(words)) ATTESTED.add(w)
      }
      if (Number.isFinite(Number(data.floor))) ATTESTED_FLOOR = Number(data.floor)
      console.log('$qjs$ attested loaded entries=' + ATTESTED.size + ' floor=' + ATTESTED_FLOOR)
    } catch (e) {
      console.error('$qjs$ attested parse error:', e.message)
    }
  } else {
    console.log('$qjs$ attested missing')
  }
}

function loadUnigramLMFromText(text) {
  const map = new Map()
  let max = 1
  if (!text) return { map, max }
  const lines = text.split(/\r?\n/)
  for (const line of lines) {
    if (!line) continue
    const parts = line.split('\t')
    if (parts.length < 2) continue
    const word = toNfc(parts[0])
    const count = Number(parts[1])
    if (!word || !Number.isFinite(count)) continue
    map.set(word, count)
    if (count > max) max = count
  }
  return { map, max }
}

/** Soft NFC for GU natives (NFC may be unavailable in some qjs builds). */
function toNfc(text) {
  if (!text) return text
  try {
    if (typeof text.normalize === 'function') return text.normalize('NFC')
  } catch (e) { /* ignore */ }
  return text
}

/** Soft demotion for illegal GU combining piles (not a full syllable rejector). */
function guOrthographyPenalty(text) {
  if (!text) return 0
  let pen = 0
  const matra = /[\u0ABE-\u0ACC\u0AE2\u0AE3]/
  const virama = '\u0ACD'
  if (matra.test(text[0])) pen += 3.0
  for (let i = 0; i < text.length - 1; i++) {
    const a = text[i]
    const b = text[i + 1]
    if (a === virama && b === virama) pen += 2.5
    if (matra.test(a) && matra.test(b)) pen += 2.0
  }
  return pen
}

/** Native-dict / stem / spell-dict validity — IndicXlit-style rescoring signal. */
function dictionaryValidity(text) {
  if (!text) return { score: 0, attested: false, evidence: 0, spellOk: false, uniStrong: false }
  text = toNfc(text)
  const uni = UNIGRAM_LM.map.get(text) || 0
  const spellOk = ATTESTED.has(text)
  let spellHit = spellOk ? ATTESTED_FLOOR : 0
  let stemHit = STEM_FREQ.get(text) || 0
  let stemReal = STEM_FREQ.get(text) || 0
  if (ATTESTED.has(text)) stemHit = Math.max(stemHit, ATTESTED_FLOOR)
  for (const suf of GU_SUFFIXES) {
    if (text.length <= suf.length + 1) continue
    if (!text.endsWith(suf)) continue
    const stem = text.slice(0, -suf.length)
    if (!stem) continue
    const stemFreq = STEM_FREQ.get(stem) || 0
    stemReal = Math.max(stemReal, stemFreq)
    stemHit = Math.max(stemHit, stemFreq)
    if (ATTESTED.has(stem)) stemHit = Math.max(stemHit, ATTESTED_FLOOR)
    for (const ext of ['ે', 'ો', 'ા', 'ી', 'ું', 'વું', 'તું', 'વા', 'શે', 'શો']) {
      const form = stem + ext
      const fu = UNIGRAM_LM.map.get(form) || 0
      const fs = STEM_FREQ.get(form) || 0
      stemHit = Math.max(stemHit, fu, fs)
      stemReal = Math.max(stemReal, fu > ATTESTED_FLOOR ? fu : 0, fs)
      if (ATTESTED.has(form)) stemHit = Math.max(stemHit, ATTESTED_FLOOR)
    }
  }
  const evidence = Math.max(uni, stemHit, spellHit)
  const uniStrong = uni > ATTESTED_FLOOR
  // Sole membership in attested.json with only floor padding (no uni/stem) ≠ DICT.
  // Any direct unigram hit (including soft floor 50) still counts — otherwise soft LM is inert.
  const attested =
    uni > 0 || stemReal > 0 || (spellOk && uniStrong)
  let virama = 0
  for (const ch of text) if (ch === '\u0ACD') virama += 1
  const viramaPenalty = virama * 0.25 + guOrthographyPenalty(text)
  const score =
    Math.log1p(uni) +
    Math.log1p(spellHit) * 0.35 +
    Math.log1p(stemHit) * (uni > 0 ? 0.35 : 0.7) -
    viramaPenalty
  return {
    score: Math.max(0, score),
    attested,
    evidence,
    spellOk,
    uniStrong,
  }
}

function normalizedScore(count, max) {
  if (!count || !max) return 0
  return Math.log1p(count) / Math.log1p(max)
}

function userBoost(count) {
  if (!count) return 0
  return Math.min(LM_WEIGHTS.user * 1.5, Math.log1p(count) / 3.5)
}

/** Extra boost when user previously committed this native for this typed roman.
 * After threshold commits, personalized tier + ceiling boost. */
function userRomanCount(typedRoman, native) {
  if (!typedRoman || !native || !USER_LEARNING || !USER_LEARNING.choices) return 0
  const nest = USER_LEARNING.choices[String(typedRoman).toLowerCase()]
  if (!nest || !nest[native]) return 0
  return nest[native].count || 0
}

function userRomanBoost(typedRoman, native, threshold) {
  const c = userRomanCount(typedRoman, native)
  if (!c) return 0
  const thr = threshold || USER_LEARNING_THRESHOLD
  if (c >= thr) return 80
  return Math.min(8.0, 2.4 * Math.log1p(c * 3))
}

function cachedScore(key) {
  if (SCORE_CACHE.has(key)) return SCORE_CACHE.get(key)
  return null
}

function setCachedScore(key, value) {
  if (SCORE_CACHE.size > SCORE_CACHE_LIMIT) {
    SCORE_CACHE.clear()
  }
  SCORE_CACHE.set(key, value)
}

const USER_LEARNING_FILE = 'gujarati.user-learning.json'
let USER_LEARNING = { version: 1, choices: {} }
let USER_LEARNING_THRESHOLD = 2
let USER_LEARNING_ENABLED = true
let LAST_COMPOSITION_ROMAN = ''
let COMMIT_CONN = null
let UPDATE_CONN = null

function learningPath(env) {
  try {
    if (env && env.userDataDir) {
      return String(env.userDataDir).replace(/\/$/, '') + '/' + USER_LEARNING_FILE
    }
  } catch (_e) {}
  return resolveUserPath('~/Library/Rime/' + USER_LEARNING_FILE)
}

function loadUserLearningOnce(env) {
  const path = learningPath(env)
  let text = ''
  try {
    if (env && typeof env.loadFile === 'function') text = env.loadFile(path) || ''
    else if (typeof read === 'function') text = read(path) || ''
  } catch (_e) {
    text = ''
  }
  try {
    const data = JSON.parse(text || '{}')
    USER_LEARNING = data && typeof data === 'object' ? data : { version: 1, choices: {} }
    if (!USER_LEARNING.choices) USER_LEARNING.choices = {}
    USER_LEARNING.version = 1
  } catch (_e) {
    USER_LEARNING = { version: 1, choices: {} }
  }
}

function writeFileAtomic(env, path, content) {
  // Patched Environment.writeFileAtomic only — no saveFile / global write fallbacks.
  if (!env || typeof env.writeFileAtomic !== 'function') {
    if (!writeFileAtomic._warned) {
      console.error('$qjs$ learning disabled: Environment.writeFileAtomic missing')
      writeFileAtomic._warned = true
    }
    return false
  }
  try {
    env.writeFileAtomic(path, content)
    return true
  } catch (e) {
    console.error('$qjs$ writeFileAtomic failed: ' + (e && e.message))
    return false
  }
}

function persistUserLearning(env) {
  const path = learningPath(env)
  // Refuse writes outside userDataDir when we can detect traversal
  try {
    if (env && env.userDataDir) {
      const root = String(env.userDataDir).replace(/\/$/, '')
      if (!path.startsWith(root + '/') && path !== root + '/' + USER_LEARNING_FILE.replace(/^.*\//, '')) {
        if (!String(path).startsWith(root)) {
          console.error('$qjs$ refuse learning write outside userDataDir')
          return
        }
      }
    }
  } catch (_e) {}
  if (!writeFileAtomic(env, path, JSON.stringify(USER_LEARNING))) {
    USER_LEARNING_ENABLED = false
  }
}

function recordUserLearningChoice(env, roman, native) {
  if (!USER_LEARNING_ENABLED) return
  if (!roman || !native) return
  if (!/[\u0A80-\u0AFF]/.test(native)) return // GU only
  if (/[\u{1F300}-\u{1FAFF}]/u.test(native)) return
  const r = String(roman).toLowerCase()
  if (!USER_LEARNING.choices[r]) USER_LEARNING.choices[r] = {}
  const nest = USER_LEARNING.choices[r]
  const cur = nest[native] || { count: 0, last_used: 0 }
  cur.count = Math.min(255, (cur.count || 0) + 1)
  cur.last_used = Date.now()
  nest[native] = cur
  // Cap 8 natives / roman
  const ents = Object.entries(nest).sort((a, b) => (b[1].last_used || 0) - (a[1].last_used || 0))
  if (ents.length > 8) USER_LEARNING.choices[r] = Object.fromEntries(ents.slice(0, 8))
  // Cap 10k romans LRU
  const keys = Object.keys(USER_LEARNING.choices)
  if (keys.length > 10000) {
    const scored = keys
      .map((k) => [k, Math.max(0, ...Object.values(USER_LEARNING.choices[k]).map((x) => x.last_used || 0))])
      .sort((a, b) => a[1] - b[1])
    for (let i = 0; i < scored.length - 10000; i++) delete USER_LEARNING.choices[scored[i][0]]
  }
  persistUserLearning(env)
}

function ensureUserLM(_path) {
  // Legacy no-op — learning uses USER_LEARNING JSON only.
}

function getContextPrevWord(env) {
  try {
    if (env && env.engine && env.engine.context) {
      const ctx = env.engine.context
      if (typeof ctx.get_commit_text === 'function') {
        const text = ctx.get_commit_text()
        return lastWord(text)
      }
      if (typeof ctx.commit_text === 'function') {
        const text = ctx.commit_text()
        return lastWord(text)
      }
      if (typeof ctx.get_preedit === 'function') {
        const text = ctx.get_preedit()
        return lastWord(text)
      }
    }
  } catch (e) {
    return ''
  }
  return ''
}

function lastWord(text) {
  if (!text || typeof text !== 'string') return ''
  const matches = text.match(/[\u0A80-\u0AFF]+|[A-Za-z]+/g)
  if (!matches || matches.length === 0) return ''
  return matches[matches.length - 1]
}

function getContextPrevWords(env) {
  try {
    if (env && env.engine && env.engine.context) {
      const ctx = env.engine.context
      let text = ''
      if (typeof ctx.get_commit_text === 'function') {
        text = ctx.get_commit_text()
      } else if (typeof ctx.commit_text === 'function') {
        text = ctx.commit_text()
      } else if (typeof ctx.get_preedit === 'function') {
        text = ctx.get_preedit()
      }
      if (!text) return []
      const matches = text.match(/[\u0A80-\u0AFF]+|[A-Za-z]+/g)
      if (!matches || matches.length === 0) return []
      return matches.slice(-2)
    }
  } catch (e) {
    return []
  }
  return []
}

// ---------------------------------------------------------------------------
// Token set for fast tokenization
// ---------------------------------------------------------------------------

const TOKEN_SET = new Set([
  // Length 3
  'chh', 'ksh', 'gny', 'jny', 'sth', 'str', 'shr',
  // Length 2
  'kh', 'gh', 'ng', 'ch', 'Th', 'Dh', 'Sh', 'ph', 'bh', 'dv', 'gy', 'gn', 'ny', 'jh',
  'aa', 'ee', 'ii', 'oo', 'uu', 'ai', 'au', 'RR',
  'th', 'dh', 'sh', 'tr', 'om',
  // Length 1
  'a', 'i', 'u', 'e', 'o',
  'k', 'g', 'j', 'T', 'D', 'N', 't', 'd', 'n', 'p', 'b', 'm', 'y', 'r', 'l', 'v', 's', 'h', 'L',
  'c', 'f', 'w', 'x', 'z',
  'R', 'E', 'O', 'M', 'H',
  '+',
])

const MAX_TOKEN_LEN = 3

/**
 * Productive conjunct pairs (C1,C2) — Apple / Google Indic / MS phonetic style.
 * Default between consonants is inherent schwa (no virama); only these form clusters.
 * Explicit virama remains available via '+' in the roman input.
 */
const PRODUCTIVE_CONJUNCTS = new Set([
  // ya-phala (વ્ય, ક્ય, …) — past participles, passives
  'v|y', 'k|y', 'g|y', 'c|y', 'ch|y', 'j|y', 't|y', 'd|y', 'n|y', 'p|y', 'b|y',
  'm|y', 'r|y', 'l|y', 's|y', 'sh|y', 'h|y', 'T|y', 'D|y',
  // ra clusters
  'p|r', 't|r', 'k|r', 'g|r', 'd|r', 'b|r', 's|r', 'sh|y', 'sh|r', 'f|r', 'ph|r',
  // va clusters
  'k|v', 't|v', 'd|v', 's|v', 'n|v', 'dh|v',
  // misc common (doc §7)
  't|n', 's|n', 's|t', 's|k', 's|th', 'd|y', 't|th',
])

function conjunctKey(a, b) {
  return a + '|' + b
}

function shouldFormConjunct(leftTok, rightTok) {
  if (!leftTok || !rightTok) return false
  if (PRODUCTIVE_CONJUNCTS.has(conjunctKey(leftTok, rightTok))) return true
  // already-atomic digraphs in CONSONANTS (ksh/gy/dv) are single tokens
  return false
}

const ANUSVARA = '\u0A82'
const U_MATRA = '\u0AC1'
const UU_MATRA = '\u0AC2'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isGujaratiConsonantCodePoint(code) {
  return code >= 0x0A95 && code <= 0x0AB9 && code !== 0x0AB1 && code !== 0x0AB4
}

function endsWithConsonantWithImplicitA(str) {
  if (str.length === 0) return false
  const lastCode = str.charCodeAt(str.length - 1)
  return isGujaratiConsonantCodePoint(lastCode)
}


function applePreferredToken(input, i) {
  // Longest-match against APPLE_PREFERRED keys
  let best = null
  let bestLen = 0
  const slice = input.slice(i)
  for (const key of Object.keys(APPLE_PREFERRED)) {
    if (key.length > bestLen && slice.startsWith(key)) {
      best = key
      bestLen = key.length
    }
  }
  if (!best) return null
  return { key: best, value: APPLE_PREFERRED[best], len: bestLen }
}

function tokenize(input) {
  const tokens = []
  let i = 0
  while (i < input.length) {
    let matched = false
    for (let len = MAX_TOKEN_LEN; len >= 1; len--) {
      if (i + len <= input.length) {
        const substr = input.substring(i, i + len)
        if (TOKEN_SET.has(substr)) {
          tokens.push(substr)
          i += len
          matched = true
          break
        }
      }
    }
    if (!matched) {
      tokens.push(input[i])
      i++
    }
  }
  return tokens
}

function transliterateTokens(tokens) {
  let result = ''

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i]
    const nextToken = tokens[i + 1]

    if (VOWEL_INDEPENDENT[token] !== undefined) {
      if (endsWithConsonantWithImplicitA(result)) {
        if (token === 'a') {
          // 'a' after consonant = implicit short 'a'; no change
        } else {
          const matra = VOWEL_MATRAS[token]
          if (matra !== undefined) {
            const consonant = result[result.length - 1]
            result = result.slice(0, -1) + consonant + matra
          } else {
            result += VOWEL_INDEPENDENT[token]
          }
        }
      } else {
        result += VOWEL_INDEPENDENT[token]
      }
    } else if (CONSONANTS[token] !== undefined) {
      const consChar = CONSONANTS[token]
      // Indic IME grammar: default inherent schwa between consonants.
      // Virama only for explicit '+' or productive conjuncts (vy, pr, tr, …).
      if (nextToken === '+') {
        result += consChar + VIRAMA
      } else if (
        nextToken !== undefined &&
        CONSONANTS[nextToken] !== undefined &&
        shouldFormConjunct(token, nextToken)
      ) {
        result += consChar + VIRAMA
      } else {
        result += consChar
      }
    } else if (token === '+') {
      if (endsWithConsonantWithImplicitA(result)) {
        result += VIRAMA
      }
      // '+' is consumed without output when not applicable
    } else if (DIGITS[token] !== undefined) {
      result += DIGITS[token]
    } else {
      result += token
    }
  }

  return result
}

/** Past-participle / nasal final -u (પોષતું, પરખાવ્યું) — Google/Apple often omit 'n'/'m'. */
function withNasalFinalU(gu) {
  if (!gu) return null
  if (gu.endsWith(U_MATRA + ANUSVARA) || gu.endsWith(UU_MATRA + ANUSVARA)) return null
  if (gu.endsWith(U_MATRA)) return gu + ANUSVARA
  return null
}

function transliterate(input) {
  const tokens = tokenize(input)
  return transliterateTokens(tokens)
}

/**
 * Apple/Google-style diphthong splits: roman `ai`/`ay`/`oi`/`ui`/`ei` often mean
 * independent ઈ/ઇ (કોઈ, જોઈ, થઈ) — not only matra ૈ / bare ી from i↔ii.
 * Constructs forms the matra transliterator cannot emit.
 */
function diphthongAlternateForms(roman) {
  const out = []
  if (!roman) return out
  const s = String(roman).toLowerCase()
  const digraphs = ['ai', 'ay', 'oi', 'ui', 'ei']
  for (const digraph of digraphs) {
    let idx = 0
    let added = 0
    while (idx <= s.length - digraph.length && added < 3) {
      const at = s.indexOf(digraph, idx)
      if (at < 0) break
      const prefix = s.slice(0, at)
      const suffix = s.slice(at + digraph.length)
      // Avoid splitting inside longer vowel runs (e.g. aai already has aa+i path).
      if (at > 0 && s[at - 1] === 'a' && digraph === 'ai') {
        idx = at + 1
        continue
      }
      const prefixGu = prefix ? transliterate(prefix) : ''
      const suffixGu = suffix ? transliterate(suffix) : ''
      const nuclei = []
      if (digraph === 'ai') {
        if (!prefixGu) {
          nuclei.push('ઐ', 'અઈ', 'અઇ', 'આઈ', 'આઇ')
        } else if (endsWithConsonantWithImplicitA(prefixGu)) {
          // gai→ગઈ/ગઇ; also aa-colored ગાઈ/ગાઇ (Apple shows both)
          nuclei.push(prefixGu + 'ઈ', prefixGu + 'ઇ')
          const withAa = prefixGu.slice(0, -1) + prefixGu.slice(-1) + VOWEL_MATRAS.aa
          nuclei.push(withAa + 'ઈ', withAa + 'ઇ')
        }
      } else if (digraph === 'ay') {
        if (!prefixGu) {
          nuclei.push('અય', 'આય')
        } else if (endsWithConsonantWithImplicitA(prefixGu)) {
          nuclei.push(prefixGu + 'ય')
          const withAa = prefixGu.slice(0, -1) + prefixGu.slice(-1) + VOWEL_MATRAS.aa
          nuclei.push(withAa + 'ય')
        }
      } else if (digraph === 'oi' || digraph === 'ui' || digraph === 'ei') {
        // joi→જોઈ, kui→કુઈ, udhei→ઉધેઈ — vowel matra + independent ઈ/ઇ
        if (endsWithConsonantWithImplicitA(prefixGu)) {
          const matraKey = digraph === 'oi' ? 'o' : digraph === 'ui' ? 'u' : 'e'
          const withMatra = prefixGu.slice(0, -1) + prefixGu.slice(-1) + VOWEL_MATRAS[matraKey]
          nuclei.push(withMatra + 'ઈ', withMatra + 'ઇ')
          if (digraph === 'ui') {
            const withUu = prefixGu.slice(0, -1) + prefixGu.slice(-1) + VOWEL_MATRAS.uu
            nuclei.push(withUu + 'ઈ', withUu + 'ઇ')
          }
        }
      }
      for (const n of nuclei) out.push(n + suffixGu)
      if (nuclei.length) added += 1
      idx = at + 1
    }
  }
  return out
}

/** All phonetic script forms to consider for one roman string (base + nasal -u + diphthongs). */
function phoneticFormsForRoman(roman) {
  // Western digits stay Arabic (2.9 / 2026), never ૨.૯.
  if (/^\d+(\.\d*)?$/.test(roman) || /^\d*\.\d+$/.test(roman)) return [String(roman)]
  const out = []
  const seen = new Set()
  function add(g) {
    if (!g || g === roman || seen.has(g)) return
    seen.add(g)
    out.push(g)
  }
  const base = transliterate(roman)
  add(base)
  add(withNasalFinalU(base))
  for (const g of diphthongAlternateForms(roman)) {
    add(g)
    add(withNasalFinalU(g))
  }
  return out
}

// ---------------------------------------------------------------------------
// Phonetic alternate form generator
// Generates alternate spellings by inserting implicit 'a' between
// consecutive consonant characters, handling variations like
// nmste → namste → namaste for dictionary lookup.
// ---------------------------------------------------------------------------

const MAX_ALT_FORMS = 96
const MAX_ALT_INSERTIONS = 2

// Phonetic confusions users actually type (macOS fuzzy mapping).
// sh↔Sh covers પોશ vs પોષ; t↔T covers કેત vs કેટ; f↔ph; endings cover િ vs ી, u vs ું.
const CONFUSION_MAP = {
  'ch': ['chh'],
  'chh': ['ch'],
  't': ['T'],
  'T': ['t'],
  'd': ['D'],
  'D': ['d'],
  's': ['sh', 'Sh'],
  'sh': ['Sh', 's'],
  'Sh': ['sh', 's'],
  'n': ['N'],
  'N': ['n'],
  'l': ['L'],
  'L': ['l'],
  'f': ['ph'],
  'ph': ['f'],
  // Apple/Google treat w as વ (vikas↔wikas)
  'v': ['w'],
  'w': ['v'],
  // Colloquial z↔j (zindabad / jindabad)
  'z': ['j'],
  'j': ['z'],
  // jñā conjunct aliases (gnan / gyaan / gnyan)
  'gn': ['gy', 'gny', 'jny'],
  'gy': ['gn', 'gny', 'jny'],
  'gny': ['gy', 'gn', 'jny'],
  'jny': ['gy', 'gn', 'gny'],
}

const ENDING_VARIANTS = {
  'i': ['ii', 'ee'],
  'ii': ['i'],
  'ee': ['i', 'ii'],
  'u': ['uu', 'un', 'um'],
  'uu': ['u'],
  'un': ['u', 'um'],
  'um': ['u', 'un'],
  'a': ['aa'],
  'aa': ['a'],
}

/** True when roman `i`/`ii`/`ee` at `iPos` is the second half of ai/oi/ui/ei (not ketli-style). */
function isDiphthongI(s, iPos) {
  if (!s || iPos <= 0) return false
  const prev = s[iPos - 1]
  return prev === 'a' || prev === 'e' || prev === 'o' || prev === 'u'
}

/** Extra roman queries for lexicon lookup (poshatu ↔ poshatun, ketli ↔ keTlii). */
function withEndingVariants(s) {
  const out = new Set([s])
  for (const [from, tos] of Object.entries(ENDING_VARIANTS)) {
    if (s.length <= from.length) continue
    if (!s.endsWith(from)) continue
    // gai→gaee/gaii would invent ગી and outrank attested ગઈ; keep i↔ii for consonant+i only.
    if ((from === 'i' || from === 'ii' || from === 'ee') && isDiphthongI(s, s.length - from.length)) {
      continue
    }
    const stem = s.slice(0, -from.length)
    for (const to of tos) out.add(stem + to)
  }
  return out
}

/** Mid-string vowel length variants (bounded) — i↔ii, a↔aa, u↔oo. */
function withMidVowelVariants(s) {
  const out = new Set([s])
  if (!s || s.length < 3) return out
  const pairs = [
    ['i', 'ii'],
    ['ii', 'i'],
    ['a', 'aa'],
    ['aa', 'a'],
    ['oo', 'u'],
    ['u', 'oo'],
    ['uu', 'oo'],
    ['oo', 'uu'],
  ]
  for (const [from, to] of pairs) {
    let idx = 0
    let added = 0
    while (idx <= s.length - from.length && added < 4) {
      const at = s.indexOf(from, idx)
      if (at < 0) break
      // Prefer interior / non-trivial positions; still allow endings
      if (at > 0) {
        // Skip ai→aii (and oi/ui/ei); diphthongs use split phonetics instead.
        if ((from === 'i' || from === 'ii') && isDiphthongI(s, at)) {
          idx = at + 1
          continue
        }
        // Avoid oui→ooi noise: don't expand bare u inside diphthong-ish ou/au.
        if (from === 'u' && (s[at - 1] === 'o' || s[at - 1] === 'a')) {
          idx = at + 1
          continue
        }
        out.add(s.slice(0, at) + to + s.slice(at + from.length))
        added += 1
      }
      idx = at + 1
    }
  }
  return out
}

/** Leading a↔aa (avo→aavo→આવો). Mid-vowel pass skips index 0. */
function withLeadingVowelVariants(s) {
  const out = new Set([s])
  if (!s || s.length < 2) return out
  if (s.startsWith('aa')) out.add('a' + s.slice(2))
  else if (s.startsWith('a') && s[1] !== 'a') out.add('aa' + s.slice(1))
  return out
}

/** Optional final schwa letter for soft lexicon keys (vikas→vikasa). */
function withTrailingSchwa(s) {
  const out = new Set([s])
  if (!s || s.length < 3) return out
  const last = s[s.length - 1]
  if (last in CONSONANTS) out.add(s + 'a')
  return out
}

/** After retroflex T/Th/D/Dh, dental n is often typed for ણ (gothni→gothaNi). */
function withRetroflexNasal(s) {
  const out = new Set([s])
  if (!s || s.length < 2) return out
  const keys = ['Th', 'Dh', 'T', 'D']
  for (const stem of keys) {
    let idx = 0
    while (idx <= s.length - stem.length - 1) {
      const at = s.indexOf(stem, idx)
      if (at < 0) break
      const nPos = at + stem.length
      if (nPos < s.length && s[nPos] === 'n') {
        out.add(s.slice(0, nPos) + 'N' + s.slice(nPos + 1))
      }
      idx = at + 1
    }
  }
  return out
}

/** Homorganic / simplified anusvara: n|m before stop → M (ં). ISO 15919 / ITRANS. */
const ANUSVARA_STOPS = [
  'kh', 'gh', 'chh', 'ch', 'jh', 'Th', 'th', 'Dh', 'dh', 'ph', 'bh',
  'k', 'g', 'c', 'j', 'T', 't', 'D', 'd', 'p', 'b',
]

function withAnusvaraNasals(s) {
  const out = new Set([s])
  if (!s) return out
  for (const nasal of ['n', 'm']) {
    let idx = 0
    while (idx < s.length) {
      const at = s.indexOf(nasal, idx)
      if (at < 0) break
      const rest = s.slice(at + 1)
      for (const stop of ANUSVARA_STOPS) {
        if (rest.startsWith(stop)) {
          out.add(s.slice(0, at) + 'M' + rest)
          break
        }
      }
      idx = at + 1
    }
  }
  return out
}

/** Visarga alias: h↔H before a consonant (dukh↔duHkh). */
function withVisargaH(s) {
  const out = new Set([s])
  if (!s) return out
  for (let i = 0; i < s.length; i++) {
    const ch = s[i]
    if (ch !== 'h' && ch !== 'H') continue
    const rest = s.slice(i + 1)
    if (!rest || !/^[kKgGcCjJTDdNtnNpPbBmyrRlLvVwsShzfx]/.test(rest)) continue
    const other = ch === 'h' ? 'H' : 'h'
    out.add(s.slice(0, i) + other + rest)
  }
  return out
}

/** Geminate doubles → explicit virama (himmat→him+mat→હિમ્મત). */
function withGeminates(s) {
  const out = new Set([s])
  if (!s || s.length < 2) return out
  const doubles = ['mm', 'nn', 'tt', 'kk', 'll', 'pp', 'bb', 'dd', 'gg', 'jj', 'ss']
  for (const d of doubles) {
    let idx = 0
    while (idx <= s.length - 2) {
      const at = s.indexOf(d, idx)
      if (at < 0) break
      out.add(s.slice(0, at) + d[0] + '+' + d[1] + s.slice(at + 2))
      idx = at + 1
    }
  }
  return out
}

/** Bounded English-loan digraph rewrites (gated). */
const ENABLE_LOAN_DIGRAPHS = true

function withLoanDigraphs(s) {
  const out = new Set([s])
  if (!ENABLE_LOAN_DIGRAPHS || !s) return out
  const lower = s.toLowerCase()
  // Only rewrite clearly Latin-looking tokens (avoid mane→man, kyare→kayar).
  if (!/(sch|tion|qu|ck|oo|ee|school|college|doctor|hospital|london)/.test(lower)) {
    return out
  }
  const reps = [
    ['sch', 'sk'],
    ['tion', 'shan'],
    ['qu', 'kv'],
    ['ck', 'k'],
    ['oo', 'uu'],
    ['ee', 'ii'],
  ]
  for (const [a, b] of reps) {
    let idx = 0
    while (idx <= lower.length - a.length) {
      const at = lower.indexOf(a, idx)
      if (at < 0) break
      out.add(lower.slice(0, at) + b + lower.slice(at + a.length))
      idx = at + 1
    }
  }
  if (lower.length >= 5 && lower.endsWith('e') && /[bcdfghjklmnpqrstvwxyz]/.test(lower[lower.length - 2])) {
    out.add(lower.slice(0, -1))
  }
  return out
}

/** Replace every occurrence position of digraph/char confusion (not only first). */
function applyConfusionOnce(s, from, to) {
  const out = []
  let idx = 0
  while (idx <= s.length - from.length) {
    const at = s.indexOf(from, idx)
    if (at < 0) break
    out.push(s.slice(0, at) + to + s.slice(at + from.length))
    idx = at + 1
  }
  return out
}

function generateAlternateForms(input) {
  const forms = new Set()
  forms.add(input)

  // Prioritize seed ending + vowel-length + one-step confusions before deep recursion
  for (const ended of withEndingVariants(input)) forms.add(ended)
  for (const mid of withMidVowelVariants(input)) forms.add(mid)
  for (const lead of withLeadingVowelVariants(input)) forms.add(lead)
  for (const trail of withTrailingSchwa(input)) forms.add(trail)
  for (const ret of withRetroflexNasal(input)) forms.add(ret)
  for (const nas of withAnusvaraNasals(input)) forms.add(nas)
  for (const gem of withGeminates(input)) forms.add(gem)
  for (const loan of withLoanDigraphs(input)) forms.add(loan)
  const keysFirst = Object.keys(CONFUSION_MAP).sort((a, b) => b.length - a.length)
  for (const from of keysFirst) {
    for (const to of CONFUSION_MAP[from]) {
      for (const replaced of applyConfusionOnce(input, from, to)) {
        forms.add(replaced)
        for (const ended of withEndingVariants(replaced)) forms.add(ended)
        for (const mid of withMidVowelVariants(replaced)) forms.add(mid)
        for (const lead of withLeadingVowelVariants(replaced)) forms.add(lead)
        for (const trail of withTrailingSchwa(replaced)) forms.add(trail)
        for (const ret of withRetroflexNasal(replaced)) forms.add(ret)
        for (const nas of withAnusvaraNasals(replaced)) forms.add(nas)
        for (const gem of withGeminates(replaced)) forms.add(gem)
        for (const loan of withLoanDigraphs(replaced)) forms.add(loan)
        if (forms.size >= MAX_ALT_FORMS) break
      }
      if (forms.size >= MAX_ALT_FORMS) break
    }
    if (forms.size >= MAX_ALT_FORMS) break
  }

  function expand(s, depth) {
    if (depth >= MAX_ALT_INSERTIONS) return
    if (forms.size >= MAX_ALT_FORMS) return
    for (let i = 0; i < s.length - 1; i++) {
      const pair = s.substring(i, i + 2)
      if ((s[i] in CONSONANTS) && (s[i + 1] in CONSONANTS) && !TOKEN_SET.has(pair)) {
        const expanded = s.slice(0, i + 1) + 'a' + s.slice(i + 1)
        if (forms.size < MAX_ALT_FORMS && !forms.has(expanded)) {
          forms.add(expanded)
          expand(expanded, depth + 1)
        }
      }
    }

    for (let i = 1; i < s.length - 1; i++) {
      if (s[i] !== 'a') continue
      if (!(s[i - 1] in CONSONANTS) || !(s[i + 1] in CONSONANTS)) continue
      const expanded = s.slice(0, i) + 'aa' + s.slice(i + 1)
      if (forms.size < MAX_ALT_FORMS && !forms.has(expanded)) {
        forms.add(expanded)
        expand(expanded, depth + 1)
      }
    }

    const keys = Object.keys(CONFUSION_MAP).sort((a, b) => b.length - a.length)
    for (const from of keys) {
      const tos = CONFUSION_MAP[from]
      for (const to of tos) {
        for (const replaced of applyConfusionOnce(s, from, to)) {
          if (forms.size < MAX_ALT_FORMS && !forms.has(replaced)) {
            forms.add(replaced)
            expand(replaced, depth + 1)
          }
        }
      }
    }

    for (const ended of withEndingVariants(s)) {
      if (forms.size < MAX_ALT_FORMS && !forms.has(ended)) {
        forms.add(ended)
        if (ended !== s) expand(ended, depth + 1)
      }
    }
    for (const mid of withMidVowelVariants(s)) {
      if (forms.size < MAX_ALT_FORMS && !forms.has(mid)) {
        forms.add(mid)
      }
    }
    for (const nas of withAnusvaraNasals(s)) {
      if (forms.size < MAX_ALT_FORMS && !forms.has(nas)) {
        forms.add(nas)
        if (nas !== s) expand(nas, depth + 1)
      }
    }
    for (const gem of withGeminates(s)) {
      if (forms.size < MAX_ALT_FORMS && !forms.has(gem)) forms.add(gem)
    }
  }

  expand(input, 0)
  for (const ended of withEndingVariants(input)) forms.add(ended)
  for (const mid of withMidVowelVariants(input)) forms.add(mid)
  for (const lead of withLeadingVowelVariants(input)) {
    forms.add(lead)
    for (const ended of withEndingVariants(lead)) forms.add(ended)
    for (const mid of withMidVowelVariants(lead)) forms.add(mid)
  }
  for (const ret of withRetroflexNasal(input)) {
    forms.add(ret)
    for (const ended of withEndingVariants(ret)) forms.add(ended)
  }
  for (const nas of withAnusvaraNasals(input)) {
    forms.add(nas)
    for (const mid of withMidVowelVariants(nas)) {
      forms.add(mid)
      for (const mid2 of withMidVowelVariants(mid)) forms.add(mid2)
    }
  }
  for (const gem of withGeminates(input)) forms.add(gem)
  for (const loan of withLoanDigraphs(input)) forms.add(loan)
  for (const vis of withVisargaH(input)) forms.add(vis)
  // Retroflex nasal on t→T confusions (gothni→goThni→goThNi)
  for (const form of Array.from(forms).slice(0, MAX_ALT_FORMS)) {
    for (const ret of withRetroflexNasal(form)) forms.add(ret)
    for (const nas of withAnusvaraNasals(form)) forms.add(nas)
    for (const vis of withVisargaH(form)) forms.add(vis)
    if (forms.size >= MAX_ALT_FORMS) break
  }
  return forms
}

/** Suffixes that are spelling noise, not real extra morphology (poshatu + n).
 * Keep nasal/visarga-like only — single vowels are too permissive (mane+i → manei).
 * Require a real stem (≥4): mi+n→min otherwise steals EXACT over phonetic મી/મિ. */
function isNearExactRomanSuffix(suf, fullKey, typedLen) {
  if (!suf) return false
  if (!/^(n|m|ng|un|um|h)$/i.test(suf)) return false
  if (typeof typedLen === 'number' && typedLen < 4) return false
  // Hit may only add the weak suffix (aad↛aadame via near-exact).
  if (typeof typedLen === 'number' && fullKey && fullKey.length > typedLen + suf.length) {
    return false
  }
  // Block English morphology completions (america→american, doctor→doctors)
  if (fullKey && /^(n|m)$/i.test(suf) && /(an|en|ian|ing|ers?|ors?|ly)$/i.test(fullKey)) {
    return false
  }
  return true
}

/** Soft-fill / weak lexicon weights must not outrank attested phonetics (Aksharantar=75). */
const LEXICON_STRONG_WEIGHT = 100

/**
 * Native is a longer morph of `baseNative` (આચાર → આચારાંગ / આડ → આડું).
 * Used to demote soft/exact morph steals over bare stems.
 */
function isNativeMorphExtension(baseNative, native) {
  if (!baseNative || !native || native === baseNative) return false
  if (!native.startsWith(baseNative)) return false
  if (native.length <= baseNative.length) return false
  return true
}

/**
 * True when `key` is `typed` with only ephemeral schwa 'a' inserted between consonants.
 * mne→mane is weak evidence; do not treat as TIER_EXACT.
 * a→aa lengthening (kyare→kyaare, avo→aavo) is NOT ephemeral — keep strong / exact.
 */
function isAInsertionOnly(typed, key) {
  if (!typed || !key || key === typed) return false
  if (key.length <= typed.length) return false
  let i = 0
  let j = 0
  let inserted = 0
  while (i < typed.length && j < key.length) {
    if (typed[i] === key[j]) {
      i += 1
      j += 1
      continue
    }
    if (key[j] === 'a') {
      // Extra a adjacent to an already-matched a is vowel lengthening, not schwa insert.
      if (j > 0 && key[j - 1] === 'a') return false
      j += 1
      inserted += 1
      continue
    }
    return false
  }
  if (i !== typed.length) return false
  while (j < key.length) {
    if (key[j] !== 'a') return false
    if (j > 0 && key[j - 1] === 'a') return false
    j += 1
    inserted += 1
  }
  return inserted > 0
}

/** IAST place-of-articulation pairs: dental ↔ retroflex (n/N, t/T, d/D, l/L). */
const IAST_PLACE_PAIR = {
  n: 'N', N: 'n', t: 'T', T: 't', d: 'D', D: 'd', l: 'L', L: 'l',
}

/** Map lexicon hit → tier. Soft / a-insertion fuzzy never get TIER_EXACT. */
function lexiconHitTier(source, weight, typedRoman, hitRoman) {
  const w = Number(weight) || 0
  const soft = w > 0 && w < LEXICON_STRONG_WEIGHT
  // Bare consonant: Apple soft-maps n→ણ etc. Keep DICT so IAST phonetics (ન/ત/…) compete.
  if (typedRoman && typedRoman.length === 1 && IAST_PLACE_PAIR[typedRoman]) {
    return TIER_DICT
  }
  if (source === 'strict' && !soft) return TIER_EXACT
  if (soft) return TIER_DICT
  // Digraph strip (vinash→vinas via sh→s) must not EXACT-steal over typed soft/long forms.
  if (source === 'fuzzy' && typedRoman && hitRoman && isDigraphStripFuzzy(typedRoman, hitRoman)) {
    return TIER_DICT
  }
  if (
    source === 'fuzzy' &&
    typedRoman.startsWith('sh') &&
    hitRoman.startsWith('s') &&
    !hitRoman.startsWith('sh')
  ) {
    return TIER_DICT
  }
  if (source === 'fuzzy' && isAInsertionOnly(typedRoman, hitRoman)) return TIER_DICT
  // Fuzzy with aa-lengthening + inserts (ank→aanak/aanka) must not EXACT-steal.
  if (source === 'fuzzy' && hitRoman && typedRoman && hitRoman.length > typedRoman.length + 1) {
    return TIER_DICT
  }
  // Productive stem expansion never gets hard EXACT (padi: પદિ from pad+i must
  // not outrank soft exact પડી). Evidence-pool DICT only.
  if (source === 'stem_matra' || source === 'stem_postfix') {
    return TIER_DICT
  }
  // Near-exact weak suffixes: EXACT only when typed has no lexicon entry.
  if (source === 'near_exact') {
    if (typedRoman && (APPLE_LEXICON.has(typedRoman) || DICT_TRIE.findExact(typedRoman))) {
      return TIER_DICT
    }
    return TIER_EXACT
  }
  if (source === 'fuzzy' || source === 'strict') return TIER_EXACT
  return TIER_DICT
}

/** True when hit is typed with a digraph collapsed (sh→s, th→t, …). */
function isDigraphStripFuzzy(typed, hit) {
  if (!typed || !hit || hit.length >= typed.length) return false
  const pairs = [
    ['chh', 'ch'], ['chh', 'c'], ['kh', 'k'], ['gh', 'g'], ['th', 't'], ['dh', 'd'],
    ['ph', 'p'], ['bh', 'b'], ['sh', 's'], ['Sh', 's'], ['Sh', 'sh'], ['jh', 'j'],
  ]
  const t = String(typed).toLowerCase()
  const h = String(hit).toLowerCase()
  for (const [long, short] of pairs) {
    if (!t.includes(long)) continue
    // Rebuild: replace one occurrence of long with short → equals hit
    let idx = 0
    while (idx <= t.length - long.length) {
      const at = t.indexOf(long, idx)
      if (at < 0) break
      if (t.slice(0, at) + short + t.slice(at + long.length) === h) return true
      idx = at + 1
    }
  }
  return false
}

/**
 * Lexicon stem + vowel matra (shabd+o → શબ્દો). Scalable for all vowel signs.
 * Stem must be a lexicon roman key ending in an inherent-a consonant native.
 */
const STEM_MATRA_SUFFIXES = [
  ['aa', '\u0ABE'], // ા
  ['ii', '\u0AC0'], // ી
  ['ee', '\u0AC0'],
  ['uu', '\u0AC2'], // ૂ
  ['oo', '\u0AC2'],
  ['ai', '\u0AC8'], // ૈ
  ['au', '\u0ACC'], // ૌ
  // bare trailing 'a' omitted — peels gharma→gharm / false stems
  ['i', '\u0ABF'], // િ
  ['u', '\u0AC1'], // ુ
  ['e', '\u0AC7'], // ે
  ['o', '\u0ACB'], // ો
]

/** Roman postpositions / morph suffixes → GU (mulya+maa → મૂલ્યમાં). Longest first. */
const STEM_POSTFIX_SUFFIXES = [
  ['maanthi', 'માંથી'],
  ['maan', 'માં'],
  ['maa', 'માં'],
  ['man', 'માં'],
  ['ma', 'માં'], // gharma → ઘરમાં; moolyama → મૂલ્યમાં
  ['valun', 'વાળું'],
  ['vali', 'વાળી'],
  ['vala', 'વાળા'],
  ['valo', 'વાળો'],
  ['thi', 'થી'],
  ['nee', 'ની'],
  ['nii', 'ની'],
  ['noo', 'નું'],
  ['nuu', 'નું'],
  ['naa', 'ના'],
  ['ni', 'ની'],
  ['nu', 'નું'],
  ['na', 'ના'],
  ['no', 'નો'],
  ['ne', 'ને'],
]

function lexiconStemMatraHits(typed) {
  const out = []
  const lower = String(typed || '').toLowerCase()
  if (lower.length < 3) return out
  for (const [suf, matra] of STEM_MATRA_SUFFIXES) {
    if (lower.length <= suf.length + 1) continue
    if (!lower.endsWith(suf)) continue
    // Don't peel vowel if preceding char is also a vowel carrier (kyaare≠kyaar+e).
    const stem = lower.slice(0, -suf.length)
    if (!stem || stem.length < 2) continue
    const last = stem[stem.length - 1]
    if ('aeiou'.includes(last)) continue
    const word = APPLE_LEXICON.get(stem) || DICT_TRIE.findExact(stem)
    if (!word) continue
    const w = lexiconWeight(stem)
    if (matra === null) {
      out.push({ roman: stem, word, weight: w, source: 'stem_matra' })
    } else if (endsWithConsonantWithImplicitA(word)) {
      out.push({ roman: stem + suf, word: word + matra, weight: Math.max(w, 100), source: 'stem_matra' })
    }
  }
  return out
}

function lookupLexiconStem(stem) {
  let word = APPLE_LEXICON.get(stem) || DICT_TRIE.findExact(stem)
  let bestRoman = stem
  let w = word ? lexiconWeight(stem) : 0
  if (word) return { word, roman: bestRoman, weight: w }
  // Fuzzy stem (mulya → moolya) without baking per word.
  for (const alt of generateAlternateForms(stem)) {
    const hit = APPLE_LEXICON.get(alt) || DICT_TRIE.findExact(alt)
    if (!hit) continue
    const ww = lexiconWeight(alt)
    if (!word || ww > w) {
      word = hit
      bestRoman = alt
      w = ww
    }
  }
  return word ? { word, roman: bestRoman, weight: w } : null
}

/** Stem + postposition (mulyama → મૂલ્ય + માં). Skips if roman stem ends in a vowel letter. */
function lexiconStemPostfixHits(typed) {
  const out = []
  const lower = String(typed || '').toLowerCase()
  if (lower.length < 4) return out
  for (const [suf, guSuf] of STEM_POSTFIX_SUFFIXES) {
    if (lower.length <= suf.length + 2) continue
    if (!lower.endsWith(suf)) continue
    const stem = lower.slice(0, -suf.length)
    if (!stem || stem.length < 2) continue
    // Allow inherent-a roman stems (moolya); reject other vowel endings (mane↛ma+ne).
    const last = stem[stem.length - 1]
    if ('eiou'.includes(last)) continue
    if (/(aa|ii|ee|uu|oo|ai|au)$/.test(stem)) continue
    const hit = lookupLexiconStem(stem)
    if (!hit) continue
    // Prefer bare inherent-a stems; allow nasal/matra stems (હિંમતમાં).
    if (
      !endsWithConsonantWithImplicitA(hit.word) &&
      !/[\u0ABE\u0AC0\u0AC1\u0AC2\u0AC7\u0AC8\u0ACB\u0ACC\u0A82]$/.test(hit.word)
    ) {
      continue
    }
    out.push({
      roman: hit.roman + suf,
      word: hit.word + guSuf,
      weight: Math.max(hit.weight, 120),
      source: 'stem_postfix',
    })
    break // longest matching postfix only
  }
  return out
}

/**
 * All roman strings to try against the Apple lexicon for this input.
 * Scalable fuzzy match — no per-word baking.
 */
function expandRomanQueries(input) {
  const q = new Set()
  const lower = input.toLowerCase()
  q.add(lower)
  q.add(input)
  for (const form of generateAlternateForms(lower)) {
    q.add(form)
    for (const ended of withEndingVariants(form)) q.add(ended)
  }
  // Weighted lattice (beam≤64) as additional roman queries
  try {
    const pairs = [
      ['sh', 'Sh'],
      ['Sh', 'sh'],
      ['s', 'sh'],
      ['t', 'T'],
      ['T', 't'],
      ['d', 'D'],
      ['D', 'd'],
      ['n', 'N'],
      ['N', 'n'],
      ['l', 'L'],
      ['L', 'l'],
      ['i', 'ii'],
      ['ii', 'i'],
      ['u', 'uu'],
      ['uu', 'u'],
      ['a', 'aa'],
      ['aa', 'a'],
      ['v', 'w'],
      ['w', 'v'],
      ['j', 'z'],
      ['z', 'j'],
    ]
    for (const { roman } of expandRomanLattice(lower, pairs, { beam: 64 })) {
      q.add(roman)
      if (q.size > 160) break
    }
  } catch (_e) {}
  return q
}

function getEnvBool(env, key, fallback) {
  try {
    if (env && env.engine && env.engine.schema && env.engine.schema.config) {
      const config = env.engine.schema.config
      if (typeof config.get_bool === 'function') {
        return config.get_bool(key) ?? fallback
      }
      if (typeof config.getBool === 'function') {
        return config.getBool(key) ?? fallback
      }
    }
  } catch (e) {
    return fallback
  }
  return fallback
}

function getEnvNumber(env, key, fallback) {
  try {
    if (env && env.engine && env.engine.schema && env.engine.schema.config) {
      const config = env.engine.schema.config
      if (typeof config.get_double === 'function') {
        const value = config.get_double(key)
        return Number.isFinite(value) ? value : fallback
      }
      if (typeof config.getDouble === 'function') {
        const value = config.getDouble(key)
        return Number.isFinite(value) ? value : fallback
      }
    }
  } catch (e) {
    return fallback
  }
  return fallback
}

function learningNativeCount(text) {
  if (!USER_LEARNING || !USER_LEARNING.choices || !text) return 0
  let n = 0
  for (const nest of Object.values(USER_LEARNING.choices)) {
    if (nest && nest[text] && nest[text].count) n += nest[text].count
  }
  return n
}

function scoreCandidate(text, prevWord, isPhonetic, env) {
  const cacheKey = text + '|' + prevWord + '|' + (isPhonetic ? '1' : '0')
  const cached = cachedScore(cacheKey)
  if (cached !== null) return cached

  const unigramCount = UNIGRAM_LM.map.get(text) || 0
  const bigramCount = prevWord ? (BIGRAM_LM.map.get(prevWord + '|' + text) || 0) : 0
  const userCount = learningNativeCount(text)
  // Do not boost pure phonetic forms — lexicon exact should win (macOS-like).
  const unigramScore = normalizedScore(unigramCount, UNIGRAM_LM.max) * LM_WEIGHTS.unigram
  const bigramScore = normalizedScore(bigramCount, BIGRAM_LM.max) * LM_WEIGHTS.bigram
  const userScore = userBoost(userCount)
  const phoneticPenalty = isPhonetic ? -0.15 : 0
  const total = unigramScore + bigramScore + userScore + phoneticPenalty
  setCachedScore(cacheKey, total)
  return total
}

function scoreCandidateWithContext(text, prevWords, isPhonetic) {
  const prevWord = prevWords.length >= 1 ? prevWords[prevWords.length - 1] : ''
  const prev2 = prevWords.length >= 2 ? prevWords[prevWords.length - 2] : ''
  const unigramCount = UNIGRAM_LM.map.get(text) || 0
  const bigramCount = prevWord ? (BIGRAM_LM.map.get(prevWord + '|' + text) || 0) : 0
  const trigramCount = prev2 && prevWord ? (TRIGRAM_LM.map.get(prev2 + '|' + prevWord + '|' + text) || 0) : 0
  const userCount = learningNativeCount(text)
  const unigramScore = normalizedScore(unigramCount, UNIGRAM_LM.max) * LM_WEIGHTS.unigram
  const bigramScore = normalizedScore(bigramCount, BIGRAM_LM.max) * LM_WEIGHTS.bigram
  const trigramScore = normalizedScore(trigramCount, TRIGRAM_LM.max) * TRIGRAM_WEIGHT
  const userScore = userBoost(userCount)
  const phoneticPenalty = isPhonetic ? -0.15 : 0
  return unigramScore + bigramScore + trigramScore + userScore + phoneticPenalty
}

function recordUserChoice(path, word, prevWord, enableUserLm, typedRoman) {
  if (!enableUserLm || !word) return
  ensureUserLM(path)
  if (!USER_LM.romanChoices) USER_LM.romanChoices = new Map()
  const nextWordCount = (USER_LM.wordCounts.get(word) || 0) + 1
  USER_LM.wordCounts.set(word, nextWordCount)
  if (prevWord) {
    const key = prevWord + '|' + word
    const nextBigramCount = (USER_LM.bigramCounts.get(key) || 0) + 1
    USER_LM.bigramCounts.set(key, nextBigramCount)
  }
  const roman = typedRoman ? String(typedRoman).toLowerCase() : ''
  if (roman) {
    if (!USER_LM.romanChoices.has(roman)) USER_LM.romanChoices.set(roman, new Map())
    const nest = USER_LM.romanChoices.get(roman)
    nest.set(word, (nest.get(word) || 0) + 1)
  }
  USER_LM_DIRTY = true
  USER_LM_PENDING_WRITES += 1
  if (USER_LM_PENDING_WRITES >= USER_FLUSH_THRESHOLD) {
    const resolvedPath = resolveUserPath(path)
    writeUserLM(resolvedPath, USER_LM.wordCounts, USER_LM.bigramCounts, USER_LM.romanChoices)
    USER_LM_DIRTY = false
    USER_LM_PENDING_WRITES = 0
  }
}

/**
 * Learn user LM only on actual commit (called from commit_on_punct_processor).
 * Flushes immediately so personalization survives process restarts.
 * @param {Environment} env
 * @param {string} word
 * @param {string} [typedRoman]
 */
export function learnCommittedChoice(env, word, typedRoman) {
  try {
    if (!word) return
    if (!USER_LEARNING_ENABLED) return
    const roman = typedRoman || getCompositionRoman(env) || LAST_COMPOSITION_ROMAN
    recordUserLearningChoice(env, roman, word)
  } catch (e) {
    console.error('$qjs$ learnCommittedChoice error:', e && e.message)
  }
}

function getCompositionRoman(env) {
  try {
    if (env && env.engine && env.engine.context) {
      const ctx = env.engine.context
      if (typeof ctx.input === 'string' && ctx.input) return String(ctx.input)
      if (typeof ctx.get_input === 'function') {
        const v = ctx.get_input()
        if (v) return String(v)
      }
      if (ctx.composition && typeof ctx.composition.input === 'string') {
        return String(ctx.composition.input)
      }
    }
  } catch (e) { /* ignore */ }
  return ''
}

/** Cheap roman distance for soft-gate ranking (prefer closer fuzzy hits). */
function romanCloseness(a, b) {
  if (!a || !b) return 0
  if (a === b) return 100
  const x = String(a).toLowerCase()
  const y = String(b).toLowerCase()
  if (x === y) return 100
  if (y.startsWith(x) || x.startsWith(y)) {
    return 80 - Math.min(40, Math.abs(x.length - y.length) * 8)
  }
  let shared = 0
  const n = Math.min(x.length, y.length)
  for (let i = 0; i < n; i++) {
    if (x[i] === y[i]) shared += 1
    else break
  }
  return Math.max(0, shared * 6 - Math.abs(x.length - y.length) * 4)
}

/** URL / email / host-looking roman → Latin-only (no script suggest). */
function looksLikeLatinLiteral(s) {
  if (!s) return false
  return /@|:\/\/|(^|\.)(com|org|net|edu|io|gov)(\b|$)/i.test(s) || /^https?:\/\//i.test(s)
}

/**
 * Numbers should stay Western/Arabic digits (2.9 → 2.9, not 2.૯ / ૨.૯).
 * Pure digit strings and decimals are Latin-first.
 */
function looksLikeAsciiNumber(s) {
  if (!s) return false
  if (/^\d+\.\d*$/.test(s) || /^\d*\.\d+$/.test(s) || /\d\.\d/.test(s)) return true
  if (/^\d+$/.test(s)) return true
  return false
}

// ---------------------------------------------------------------------------
// Rime Translator
// ---------------------------------------------------------------------------

/**
 * @implements {Translator}
 */
export class GujaratiTranslator {
  constructor(env) {
    console.log('$qjs$ gujarati translator init')
    loadLexiconBlob(env)
    loadLanguageModels(env)
    loadEmojiKeywords(env)
    // enable_user_learning is authoritative when present; else fall back to enable_user_lm.
    // Explicit false always wins (never OR with legacy true).
    {
      let learningKeySet = false
      try {
        const config = env && env.engine && env.engine.schema && env.engine.schema.config
        if (config) {
          const raw =
            typeof config.get_bool === 'function'
              ? config.get_bool('translator/enable_user_learning')
              : typeof config.getBool === 'function'
                ? config.getBool('translator/enable_user_learning')
                : null
          if (raw === true || raw === false) {
            USER_LEARNING_ENABLED = raw
            learningKeySet = true
          }
        }
      } catch (_e) {}
      if (!learningKeySet) {
        USER_LEARNING_ENABLED = getEnvBool(env, 'translator/enable_user_lm', true)
      }
    }
    USER_LEARNING_THRESHOLD = Math.max(1, Math.floor(getEnvNumber(env, 'translator/user_learning_threshold', 2)))
    if (USER_LEARNING_ENABLED) loadUserLearningOnce(env)

    try {
      const ctx = env && env.engine && env.engine.context
      if (ctx && ctx.updateNotifier && typeof ctx.updateNotifier.connect === 'function') {
        UPDATE_CONN = ctx.updateNotifier.connect(() => {
          try {
            LAST_COMPOSITION_ROMAN = String(ctx.input || '').toLowerCase()
          } catch (_e) {}
        })
      }
      if (ctx && ctx.commitNotifier && typeof ctx.commitNotifier.connect === 'function') {
        COMMIT_CONN = ctx.commitNotifier.connect(() => {
          try {
            let native = ''
            try {
              if (ctx.commitHistory && ctx.commitHistory.last) {
                const last = ctx.commitHistory.last
                native = String((last && (last.text || last)) || '')
              }
            } catch (_e) {}
            if (!native && typeof ctx.getCommitText === 'function') {
              native = String(ctx.getCommitText() || '')
            }
            const roman = LAST_COMPOSITION_ROMAN || String(ctx.input || '').toLowerCase()
            if (native && roman) recordUserLearningChoice(env, roman, native)
          } catch (e) {
            console.error('$qjs$ commit learn error: ' + (e && e.message))
          }
        })
      }
    } catch (e) {
      console.error('$qjs$ notifier wire error: ' + (e && e.message))
    }
  }

  finalizer() {
    try {
      if (COMMIT_CONN && typeof COMMIT_CONN.disconnect === 'function') COMMIT_CONN.disconnect()
      if (UPDATE_CONN && typeof UPDATE_CONN.disconnect === 'function') UPDATE_CONN.disconnect()
    } catch (_e) {}
    COMMIT_CONN = null
    UPDATE_CONN = null
    console.log('$qjs$ gujarati translator finit')
  }

  /**
   * @param {string} input
   * @param {Segment} segment
   * @param {Environment} env
   * @returns {Array<Candidate>}
   */
  translate(input, segment, env) {
    try {
      if (!input || input.length === 0) {
        return []
      }

      if (looksLikeLatinLiteral(input) || looksLikeAsciiNumber(input)) {
        const cand = new Candidate('latin', segment.start, segment.end, input, '', 100)
        cand.quality = 100
        return [cand]
      }

      loadLexiconBlob(env)
      loadLanguageModels(env)
      loadEmojiKeywords(env)

      const enableUserLm = USER_LEARNING_ENABLED
      USER_LEARNING_THRESHOLD = Math.max(
        1,
        Math.floor(getEnvNumber(env, 'translator/user_learning_threshold', USER_LEARNING_THRESHOLD))
      )
      // No per-keystroke user-file I/O — learning loaded once at init / updated on commit.
      const hardGate = getEnvBool(env, 'translator/lexicon_hard_gate', true)
      const fuzzyExactSoft = getEnvBool(env, 'translator/fuzzy_exact_soft', true)
      const includeLatin = getEnvBool(env, 'translator/include_latin', true)
      const emojiEnable = getEnvBool(env, 'translator/emoji_enable', true)
      const maxPrefix = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_prefix', 3)))
      const maxPhonetic = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_phonetic', 4)))
      const maxEmoji = Math.max(0, Math.floor(getEnvNumber(env, 'translator/max_emoji', 2)))
      const maxCandidates = Math.max(1, Math.floor(getEnvNumber(env, 'translator/max_candidates', 6)))
      LM_WEIGHTS.unigram = getEnvNumber(env, 'translator/lm_unigram_weight', LM_WEIGHTS.unigram)
      LM_WEIGHTS.bigram = getEnvNumber(env, 'translator/lm_bigram_weight', LM_WEIGHTS.bigram)
      LM_WEIGHTS.user = getEnvNumber(env, 'translator/lm_user_weight', LM_WEIGHTS.user)
      TRIGRAM_WEIGHT = getEnvNumber(env, 'translator/lm_trigram_weight', TRIGRAM_WEIGHT)
      const prevWords = getContextPrevWords(env)
      const prevWord = prevWords.length > 0 ? prevWords[prevWords.length - 1] : ''
      const lower = input.toLowerCase()
      const seen = new Set()
      const items = []

      function pushCand(text, comment, quality, tier, isPhonetic, romanKey, exactSource) {
        if (!text) return false
        if (seen.has(text)) {
          // Upgrade tier if a stronger source rediscovers the same native form.
          for (let i = 0; i < items.length; i++) {
            const it = items[i]
            if (it.candidate.text !== text) continue
            if (tier < it.tier) {
              it.tier = tier
              it.exactSource = exactSource || it.exactSource
              it.romanKey = romanKey || it.romanKey
              it.weight = Math.max(it.weight || 0, tier === TIER_EMOJI ? quality : lexiconWeight(romanKey || lower))
              it.closeness = Math.max(it.closeness || 0, romanCloseness(lower, romanKey || lower))
              it.candidate.comment = comment || it.candidate.comment
              return true
            }
            return false
          }
          return false
        }
        seen.add(text)
        const kind = tier === TIER_EMOJI ? 'emoji' : 'gujarati'
        const cand = new Candidate(kind, segment.start, segment.end, text, comment || '', quality)
        cand.quality = quality
        items.push({
          candidate: cand,
          tier,
          isPhonetic: !!isPhonetic,
          romanKey: romanKey || lower,
          weight: tier === TIER_EMOJI ? quality : lexiconWeight(romanKey || lower),
          exactSource: exactSource || null,
          closeness: romanCloseness(lower, romanKey || lower),
        })
        return true
      }

      // GENERAL fuzzy lexicon lookup: expand roman confusions/endings, then hit 96k Apple dict.
      // poshatu → poshatun → પોષતું; ketli → keTlii → (phonetic) કેટલી + unigram boost.
      const romanQueries = expandRomanQueries(input)
      const altForms = generateAlternateForms(lower)

      const exc = APPLE_EXCEPTIONS.get(lower) || APPLE_EXCEPTIONS.get(input)
      if (exc) {
        pushCand(exc, input, 999, TIER_EXACT, false, lower, 'strict')
      }

      const exactHits = []
      for (const q of romanQueries) {
        const word = APPLE_LEXICON.get(q) || DICT_TRIE.findExact(q)
        if (!word) continue
        const source = q === lower || q === input ? 'strict' : 'fuzzy'
        exactHits.push({
          roman: q,
          word,
          weight: Math.max(lexiconWeight(q), q === lower ? 1 : 0),
          source,
        })
      }
      exactHits.sort((a, b) => {
        // Prefer typed exact over fuzzy so a→aa soft keys cannot hide strict (kyare).
        const as = a.source === 'strict' ? 0 : 1
        const bs = b.source === 'strict' ? 0 : 1
        if (as !== bs) return as - bs
        return b.weight - a.weight || a.roman.length - b.roman.length
      })
      const typedForTier = input.length === 1 ? input : lower
      for (const hit of exactHits) {
        const q = hit.roman === lower ? 950 : 880
        const tier = lexiconHitTier(hit.source, hit.weight, typedForTier, hit.roman)
        pushCand(
          hit.word,
          hit.roman === lower ? input : hit.roman,
          q + Math.min(40, Math.log1p(hit.weight) * 5),
          tier,
          false,
          hit.roman,
          hit.source
        )
      }

      // Lexicon stem + vowel matra (shabd+o → શબ્દો) for all vowel signs.
      for (const hit of lexiconStemMatraHits(lower)) {
        const tier = lexiconHitTier('stem_matra', hit.weight, typedForTier, hit.roman)
        pushCand(hit.word, input, 920 + Math.min(40, Math.log1p(hit.weight) * 5), tier, false, hit.roman, 'stem_matra')
      }
      // Lexicon stem + postposition (mulyamaa → મૂલ્યમાં).
      for (const hit of lexiconStemPostfixHits(lower)) {
        const tier = lexiconHitTier('stem_postfix', hit.weight, typedForTier, hit.roman)
        pushCand(hit.word, input, 930 + Math.min(40, Math.log1p(hit.weight) * 5), tier, false, hit.roman, 'stem_postfix')
      }

      // Near-exact lexicon: typed + weak suffix (poshatu→poshatun).
      // Only from the typed roman (not a→aa expansions: ank↛aankh), and only when
      // typed has no lexicon entry — otherwise ghar+m/gnan+m steal EXACT over घર/જ્ઞાન.
      const typedInLex =
        APPLE_LEXICON.has(lower) ||
        APPLE_LEXICON.has(input) ||
        !!DICT_TRIE.findExact(lower) ||
        !!DICT_TRIE.findExact(input)
      if (!typedInLex) {
        for (const seed of [lower, input]) {
          if (!seed || seed.length < 2) continue
          for (const entry of DICT_TRIE.findPrefixEntries(seed, 12)) {
            if (!entry || !entry.value) continue
            if (!entry.key.startsWith(seed)) continue
            const suf = entry.key.slice(seed.length)
            if (!isNearExactRomanSuffix(suf, entry.key, seed.length)) continue
            const w = lexiconWeight(entry.key)
            const tier = lexiconHitTier('near_exact', w, typedForTier, entry.key)
            pushCand(entry.value, input, 900 + Math.min(50, Math.log1p(w) * 6), tier, false, entry.key, 'near_exact')
          }
        }
      }

      const exactItems = items.filter((x) => x.tier === TIER_EXACT)
      const exactCount = exactItems.length
      const hasStrictExact = exactItems.some((x) => x.exactSource === 'strict')
      // Weak fuzzy EXACT only (rare after soft demotion): still allow attested phonetics.
      const softExactOnly =
        fuzzyExactSoft &&
        exactCount > 0 &&
        !hasStrictExact &&
        exactItems.every((x) => (x.weight || 0) < LEXICON_STRONG_WEIGHT)

      // Latin only after we know exact/dict tiers will sort above it
      if (includeLatin) {
        pushCand(input, '', 400, TIER_LATIN, false, lower, null)
      }

      // Generate phonetics, then RESCORE with native wordlist/stems/spell-dicts.
      // Indic IME grammar: schwa-default + productive conjuncts + nasal final -u.
      const phoneticForms = []
      const seenPhon = new Set()
      function addPhon(g) {
        if (!g || g === input || g === lower || seenPhon.has(g) || seen.has(g)) return
        seenPhon.add(g)
        phoneticForms.push(g)
      }
      for (const g of phoneticFormsForRoman(input)) addPhon(g)
      // IAST place twin for bare consonants (n↔N → ન and ણ both in menu).
      if (input.length === 1 && IAST_PLACE_PAIR[input]) {
        for (const g of phoneticFormsForRoman(IAST_PLACE_PAIR[input])) addPhon(g)
      } else if (lower.length === 1 && IAST_PLACE_PAIR[lower]) {
        for (const g of phoneticFormsForRoman(IAST_PLACE_PAIR[lower])) addPhon(g)
      }
      for (const form of altForms) {
        if (form.toLowerCase() === lower) continue
        for (const g of phoneticFormsForRoman(form)) addPhon(g)
      }

      const phonScored = []
      for (const text of phoneticForms) {
        if (seen.has(text)) continue
        const known = KNOWN_WORDS.has(text)
        const validity = dictionaryValidity(text)
        // Hard-gate: drop invented phonetics when lexicon EXACT exists; still keep
        // attested / spell-dict forms (n→ણ exact must not hide dental ન).
        // Soft-fill / a-insertion hits are TIER_DICT (not EXACT), so exactCount stays 0 and
        // high-frequency phonetics can outrank them (mne → મને over soft mane→માને).
        if (hardGate && exactCount > 0 && !known) {
          if (hasStrictExact || softExactOnly) {
            if (!validity.attested && !validity.spellOk) continue
          } else {
            continue
          }
        }
        phonScored.push({ text, known, validity })
      }
      phonScored.sort((a, b) => {
        // Direct unigram hit beats stem-only / floor-attested phonetic cousins.
        const uniA = UNIGRAM_LM.map.get(a.text) || 0
        const uniB = UNIGRAM_LM.map.get(b.text) || 0
        if ((uniA > 0) !== (uniB > 0)) return uniA > 0 ? -1 : 1
        if (a.validity.spellOk !== b.validity.spellOk) return a.validity.spellOk ? -1 : 1
        if (a.validity.attested !== b.validity.attested) return a.validity.attested ? -1 : 1
        if (uniB !== uniA) return uniB - uniA
        if (b.validity.score !== a.validity.score) return b.validity.score - a.validity.score
        return 0
      })

      let phoneticCap = maxPhonetic
      const hasStrongExact = exactItems.some(
        (x) => (x.weight || 0) >= LEXICON_STRONG_WEIGHT && x.exactSource === 'strict'
      )
      if (hasStrongExact) phoneticCap = Math.min(phoneticCap, 2)

      let phoneticAdded = 0
      let uniBackedPhon = 0
      for (const item of phonScored) {
        if (phoneticAdded >= phoneticCap) break
        const uniHit = UNIGRAM_LM.map.get(item.text) || 0
        // Once we have uni-backed DICT phonetics, skip stem-only floor cousins.
        if (uniBackedPhon >= 2 && uniHit <= ATTESTED_FLOOR && !item.validity.uniStrong) {
          continue
        }
        const tier = item.validity.attested ? TIER_DICT : TIER_PHONETIC
        const q = item.validity.attested
          ? 700 + Math.min(99, item.validity.score * 12)
          : (item.known ? 300 : 200)
        if (pushCand(item.text, input, q, tier, true, lower, null)) {
          phoneticAdded += 1
          if (item.validity.uniStrong || uniHit > ATTESTED_FLOOR) uniBackedPhon += 1
        }
      }

      if (exactCount === 0 && phoneticAdded === 0) {
        const fallback = phoneticFormsForRoman(input)[0]
        if (fallback && fallback !== input) {
          const v = dictionaryValidity(fallback)
          pushCand(fallback, input, v.attested ? 720 : 250, v.attested ? TIER_DICT : TIER_PHONETIC, true, lower, null)
        }
      }

      if (input.length >= 2 && maxPrefix > 0) {
        const prefixSeeds = new Set([lower])
        for (const q of romanQueries) {
          if (q.length >= 2) prefixSeeds.add(q)
        }
        const prefixEntries = []
        for (const seed of prefixSeeds) {
          for (const entry of DICT_TRIE.findPrefixEntries(seed, Math.max(maxPrefix * 3, 16))) {
            prefixEntries.push(entry)
          }
        }
        prefixEntries.sort((a, b) => lexiconWeight(b.key) - lexiconWeight(a.key))
        let prefixAdded = 0
        for (const entry of prefixEntries) {
          if (prefixAdded >= maxPrefix) break
          if (!entry || !entry.value) continue
          if (seen.has(entry.value)) continue
          let suffix = ''
          if (entry.key.startsWith(lower)) suffix = entry.key.slice(lower.length)
          else {
            suffix = entry.key.length > lower.length ? entry.key.slice(lower.length) : ''
          }
          const w = lexiconWeight(entry.key)
          if (entry.key.startsWith(lower) && !typedInLex && isNearExactRomanSuffix(suffix, entry.key, lower.length)) {
            const tier = lexiconHitTier('near_exact', w, lower, entry.key)
            if (pushCand(entry.value, input, 860 + Math.min(40, Math.log1p(w) * 5), tier, false, entry.key, 'near_exact')) {
              prefixAdded += 1
            }
            continue
          }
          if (entry.key === lower) continue
          const comment = suffix ? ('~' + suffix) : input
          if (pushCand(entry.value, comment, 80 + Math.min(40, Math.log1p(w) * 5), TIER_PREFIX, false, entry.key, null)) {
            prefixAdded += 1
          }
        }
      }

      // Emoji suggestions from English / Gujarati-roman keywords (never beat script tiers).
      if (emojiEnable && maxEmoji > 0 && EMOJI_BY_ROMAN.size > 0) {
        const emojiHits = []
        const seenEmoji = new Set()
        function queueEmoji(list, via) {
          if (!list) return
          for (const it of list) {
            if (!it || !it.e || seenEmoji.has(it.e) || seen.has(it.e)) continue
            seenEmoji.add(it.e)
            emojiHits.push({ emoji: it.e, weight: it.w || 100, via })
          }
        }
        queueEmoji(EMOJI_BY_ROMAN.get(lower), lower)
        for (const q of romanQueries) {
          if (q !== lower) queueEmoji(EMOJI_BY_ROMAN.get(q), q)
        }
        // Native forms already in the menu (e.g. પ્રેમ from prem)
        for (const item of items) {
          if (item.tier === TIER_EMOJI) continue
          queueEmoji(EMOJI_BY_NATIVE.get(item.candidate.text), item.candidate.text)
          if (item.romanKey) queueEmoji(EMOJI_BY_ROMAN.get(item.romanKey), item.romanKey)
        }
        emojiHits.sort((a, b) => b.weight - a.weight)
        let emojiAdded = 0
        for (const hit of emojiHits) {
          if (emojiAdded >= maxEmoji) break
          if (pushCand(hit.emoji, 'emoji', 50 + Math.min(40, Math.log1p(hit.weight) * 4), TIER_EMOJI, false, lower, null)) {
            emojiAdded += 1
          }
        }
      }

      if (items.length === 0) return []

      const scored = items.map((item, index) => {
        const text = item.candidate.text || ''
        const lm = item.tier === TIER_EMOJI
          ? Math.log1p(item.weight || 0) * 0.2
          : scoreCandidateWithContext(text, prevWords, item.isPhonetic)
        const freq = Math.log1p(item.weight || 0) * 0.35
        const validity = item.tier === TIER_EMOJI
          ? { score: 0, attested: false, evidence: 0, spellOk: false }
          : dictionaryValidity(text)
        const dictBoost = validity.attested ? validity.score * 1.4 : 0
        const spellBoost = validity.spellOk ? 0.35 : 0
        const closeBoost = (item.closeness || 0) * 0.01
        const unigramCount = UNIGRAM_LM.map.get(text) || 0
        const uniBoost = Math.log1p(unigramCount) * 0.55
        let score = lm + freq + dictBoost + spellBoost + closeBoost + uniBoost
        let tier = item.tier
        const isLex =
          item.exactSource === 'strict' ||
          item.exactSource === 'fuzzy' ||
          item.exactSource === 'near_exact' ||
          item.exactSource === 'stem_matra' ||
          item.exactSource === 'stem_postfix'
        if (isLex && (item.weight || 0) > 0 && (item.weight || 0) < LEXICON_STRONG_WEIGHT && unigramCount < 150) {
          score -= freq * 0.85 + 2.8
        }
        // Soft typed lexicon only when a digraph-strip fuzzy competes (vinash vs vinas).
        const typedLex = APPLE_LEXICON.get(lower) || APPLE_EXCEPTIONS.get(lower) || DICT_TRIE.findExact(lower)
        const typedW = lexiconWeight(lower)
        if (typedLex === text && typedW > 0 && typedW < LEXICON_STRONG_WEIGHT) {
          let hasStrip = false
          for (const it of items) {
            if (it.romanKey && isDigraphStripFuzzy(lower, it.romanKey)) {
              hasStrip = true
              break
            }
          }
          if (hasStrip) score += 3.2
        }
        // Prefer Apple bare stems over morph extensions (aachar→આચાર vs આચારાંગ).
        // Do not boost soft typed keys (swagat) or bare IAST letters (n→ણ).
        const bareIast = input.length === 1 && IAST_PLACE_PAIR[input]
        if (typedLex && typedW >= LEXICON_STRONG_WEIGHT && !bareIast) {
          let competingMorph = false
          for (const it of items) {
            if (isNativeMorphExtension(typedLex, it.candidate.text)) {
              competingMorph = true
              break
            }
          }
          if (text === typedLex && competingMorph) {
            score += 6.5
          } else if (isNativeMorphExtension(typedLex, text)) {
            score -= 8.5
            if (tier === TIER_EXACT) tier = TIER_DICT
          }
        }
        // Near-exact nasal morph (aad→aadun→આડું) loses to bare typed stem when present.
        if (
          item.exactSource === 'near_exact' &&
          typedLex &&
          typedW >= LEXICON_STRONG_WEIGHT &&
          text !== typedLex &&
          item.romanKey &&
          item.romanKey.length > lower.length
        ) {
          score -= 7.0
          if (tier === TIER_EXACT) tier = TIER_DICT
        }
        // Closeness: prefer lexicon romans equal to typed over longer fuzzy keys.
        if (isLex && item.romanKey === lower && typedW >= LEXICON_STRONG_WEIGHT) score += 2.0
        else if (isLex && item.romanKey && item.romanKey.length > lower.length + 1) score -= 1.5
        // Personalization: threshold commits → dedicated tier above Exact.
        if (enableUserLm) {
          const uc = userRomanCount(lower, text)
          if (uc >= USER_LEARNING_THRESHOLD) {
            tier = TIER_PERSONALIZED
            score += userRomanBoost(lower, text, USER_LEARNING_THRESHOLD)
          } else if (uc > 0) {
            score += userRomanBoost(lower, text, USER_LEARNING_THRESHOLD)
          }
        }
        if (text.includes('ય') && !lower.includes('y')) score -= 4.0
        // IAST case for bare place-contrast letters: n→ન over ણ, N→ણ over ન (same for t/d/l).
        if (input.length === 1 && IAST_PLACE_PAIR[input]) {
          const dental = { n: 'ન', t: 'ત', d: 'દ', l: 'લ', N: 'ણ', T: 'ટ', D: 'ડ', L: 'ળ' }
          const prefer = dental[input]
          const twin = dental[IAST_PLACE_PAIR[input]]
          if (prefer && text === prefer) score += 2.5
          else if (twin && text === twin) score -= 0.35
        }
        if (lower.includes('d') && !/(^|[^a-z])D/.test(lower)) {
          if (text.includes('ડ') && !text.includes('દ')) score -= 1.2
          if (text.includes('દ')) score += 0.5
        }
        if (lower.startsWith('sh')) {
          if (text.startsWith('શ')) score += 3.0
          else if (text.startsWith('સ')) score -= 3.0 + uniBoost * 0.5
        } else if (!lower.includes('sh') && lower.includes('s')) {
          if (text.includes('શ') && !text.includes('ષ')) score -= 0.55
          if (text.includes('સ') && !text.includes('શ')) score += 0.15
        }
        if (lower.includes('z') && !lower.includes('j')) {
          if (text.startsWith('ઝ')) score += 0.5
          else if (text.startsWith('જ')) score -= 0.35
        }
        if (/(mm|nn|tt|kk|ll)/.test(lower)) {
          if (text.includes('\u0ACD')) score += 5.5
          if (text.includes(ANUSVARA) && !text.includes('\u0ACD')) {
            score -= 6.5 + uniBoost * 1.15
            if (tier === TIER_EXACT) tier = TIER_DICT
          }
        } else if (text.includes(ANUSVARA) && /n[kgcjtdTDpb]/.test(lower)) {
          score += 0.35
        }
        if (lower.startsWith('aa')) {
          // Typed aa… → prefer આ over soft/fuzzy અ… (aadas→આડસ not અડાસ).
          if (text.startsWith('આ')) score += 3.5
          else if (text.startsWith('અ')) {
            score -= 4.0
            if (tier === TIER_EXACT) tier = TIER_DICT
          }
        } else if (
          /^(?:[kgcjtdTDpbnmylrsvwxyz]|ch|kh|gh|jh|th|dh|ph|bh|sh|Sh|tr|dr)a(?!a)/i.test(lower)
        ) {
          // Short-a onset + another later `a`: demote native that ONLY long-a's the
          // onset (પારખવ્યું) — not words that also lengthen later (બાંદા / નાહ્યા).
          const leadLong =
            text.startsWith('આ') || /^[\u0A95-\u0AB9]\u0ABE/.test(text)
          if (leadLong) {
            const rest = text.startsWith('આ') ? text.slice(1) : text.slice(2)
            if (!rest.includes('ા') && /a(?!a)/.test(lower.slice(2))) {
              score -= 3.8
            }
          }
        }
        const aVowels = (lower.match(/a+/g) || []).length
        let aa = 0
        for (const ch of text) if (ch === 'ા') aa += 1
        let effectiveAa = aa
        if (text.endsWith('ા') && !lower.endsWith('a') && !lower.endsWith('aa')) {
          effectiveAa = Math.max(0, effectiveAa - 1)
          score -= 1.6
        }
        if (aVowels >= 1 && lower.slice(1).includes('a')) {
          score += 0.2 * effectiveAa
          if (aVowels >= 2 && effectiveAa >= 2) score += 2.5
          else if (aVowels >= 2 && effectiveAa < 2) score -= 1.2
        }
        if (text.length < lower.length * 0.7) score -= 2.0
        return { ...item, score, validity, index, tier }
      })

      // Soft typed exact beats stem_matra only (padi → પડી > પદિ). Never over
      // productive stem_postfix (gharma / mulyama keep માં forms).
      const hasStemMatra = scored.some((x) => x.exactSource === 'stem_matra')
      const hasStemPostfix = scored.some((x) => x.exactSource === 'stem_postfix')
      const typedW = lexiconWeight(lower)
      for (const item of scored) {
        if (
          item.romanKey === lower &&
          typedW > 0 &&
          typedW < LEXICON_STRONG_WEIGHT &&
          (item.exactSource === 'strict' || item.exactSource === 'fuzzy') &&
          item.tier === TIER_DICT &&
          !item.isPhonetic &&
          hasStemMatra &&
          !hasStemPostfix
        ) {
          item.score += 5.5
        }
        if (item.exactSource === 'stem_matra' && typedW > 0 && typedW < LEXICON_STRONG_WEIGHT) {
          item.score -= 2.0
        }
        if (item.exactSource === 'stem_postfix' && (item.weight || 0) >= LEXICON_STRONG_WEIGHT) {
          item.score += 4.5
        }
      }

      scored.sort((a, b) => {
        if (a.tier !== b.tier) return a.tier - b.tier
        if (b.score !== a.score) return b.score - a.score
        if ((b.closeness || 0) !== (a.closeness || 0)) return (b.closeness || 0) - (a.closeness || 0)
        if ((b.weight || 0) !== (a.weight || 0)) return (b.weight || 0) - (a.weight || 0)
        return a.index - b.index
      })

      // User LM is learned on commit only (see learnCommittedChoice / commit_on_punct).
      void enableUserLm

      // Display layout: GU #1 → Latin #2 (fixed) → remaining GU → prefix → emoji.
      // Linguistic tier sort happens above; quality is assigned after layout.
      const gu = []
      const latin = []
      const prefix = []
      const emoji = []
      for (const item of scored) {
        if (item.tier === TIER_LATIN) latin.push(item)
        else if (item.tier === TIER_PREFIX) prefix.push(item)
        else if (item.tier === TIER_EMOJI) emoji.push(item)
        else gu.push(item)
      }
      const laid = []
      if (gu.length) {
        laid.push(gu[0])
        if (includeLatin) {
          if (latin.length) laid.push(latin[0])
          else {
            const cand = new Candidate('latin', segment.start, segment.end, input, '', 400)
            laid.push({
              candidate: cand,
              tier: TIER_LATIN,
              isPhonetic: false,
              romanKey: lower,
              weight: 0,
              exactSource: null,
              closeness: 1,
              score: 0,
              index: -1,
            })
          }
        }
        for (let i = 1; i < gu.length; i++) laid.push(gu[i])
      } else if (includeLatin && latin.length) {
        laid.push(latin[0])
      }
      for (const x of prefix) laid.push(x)
      for (const x of emoji) laid.push(x)

      const sortedCandidates = laid.map((item, rank) => {
        const c = item.candidate
        // TIER_EMOJI=TIER_MAX → base 0 so script candidates always outrank emoji.
        c.quality = (TIER_MAX - item.tier) * 200 + Math.max(0, 180 - rank)
        return c
      })

      // Hard cap menu size (page_size alone still allows paging past soft limits).
      return sortedCandidates.length > maxCandidates
        ? sortedCandidates.slice(0, maxCandidates)
        : sortedCandidates
    } catch (e) {
      console.error('$qjs$ translate error:', e.message)
      return []
    }
  }
}
