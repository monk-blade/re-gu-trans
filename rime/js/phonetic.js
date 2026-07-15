/**
 * Phonetic / fuzzy generation + weighted lattice (beam ≤ 64).
 * Multi-pass low-cost transforms; expensive inventions need attestation.
 */
export const PHONETIC_MODULE = 3

export const DEFAULT_LATTICE = {
  beam: 64,
  costs: {
    typed: 0,
    vowel_length: 1,
    case_place: 1.5,
    dental_retroflex: 2,
    aspirate: 2.5,
    digraph: 2,
    gemination: 2.2,
    anusvara: 2.0,
    loan_o: 2.5,
    conjunct_glide: 3.0,
    intervocalic_invent: 8,
  },
}

/** Full confusion families (aligned with engine CONFUSION_MAP). */
export const DEFAULT_CONFUSION_PAIRS = [
  ['sh', 'Sh'],
  ['Sh', 'sh'],
  ['s', 'sh'],
  ['sh', 's'],
  ['s', 'Sh'],
  ['ch', 'chh'],
  ['chh', 'ch'],
  ['t', 'T'],
  ['T', 't'],
  ['d', 'D'],
  ['D', 'd'],
  ['n', 'N'],
  ['N', 'n'],
  ['l', 'L'],
  ['L', 'l'],
  ['f', 'ph'],
  ['ph', 'f'],
  ['v', 'w'],
  ['w', 'v'],
  ['z', 'j'],
  ['j', 'z'],
  ['i', 'ii'],
  ['ii', 'i'],
  ['i', 'ee'],
  ['ee', 'i'],
  ['u', 'uu'],
  ['uu', 'u'],
  ['u', 'oo'],
  ['oo', 'u'],
  ['u', 'un'],
  ['un', 'u'],
  ['a', 'aa'],
  ['aa', 'a'],
  ['o', 'au'],
  ['au', 'o'],
  ['gn', 'gy'],
  ['gy', 'gn'],
  ['gy', 'gny'],
  ['gny', 'gy'],
  ['gy', 'jny'],
  ['jny', 'gy'],
]

function pairCost(a, b, costs) {
  const ab = a + b
  if (a === 'o' || b === 'o' || a === 'au' || b === 'au') return costs.loan_o || 2.5
  if (/n$|m$|M/.test(a) || /n$|m$|M/.test(b)) return costs.anusvara || 2.0
  if (a.length !== b.length && /^(i|ii|ee|u|uu|oo|a|aa)/.test(a + b)) return costs.vowel_length
  if (/[TDNL]/.test(ab)) return costs.dental_retroflex
  if (/h/i.test(ab) && (a.includes('h') || b.includes('h'))) return costs.aspirate
  if (a === b + b || b === a + a) return costs.gemination || 2.2
  if (/gn|gy|jny|dv|ksh/.test(ab)) return costs.conjunct_glide || 3.0
  return costs.digraph
}

/**
 * Multi-pass beam lattice over confusion pairs (passes=2, beam≤64).
 * Returns [{roman, cost}] sorted by cost.
 */
export function expandRomanLattice(typed, confusionPairs, latticePolicy) {
  const policy = Object.assign({}, DEFAULT_LATTICE, latticePolicy || {})
  const costs = Object.assign({}, DEFAULT_LATTICE.costs, policy.costs || {})
  const beam = Math.min(64, Math.max(1, policy.beam || 64))
  const passes = Math.min(3, Math.max(1, policy.passes || 2))
  const lower = String(typed || '').toLowerCase()
  if (!lower) return []

  const pairs = confusionPairs && confusionPairs.length ? confusionPairs : DEFAULT_CONFUSION_PAIRS
  /** @type {Map<string, number>} */
  let frontier = new Map([[lower, costs.typed]])

  for (let pass = 0; pass < passes; pass++) {
    const next = new Map(frontier)
    for (const [roman, cost] of frontier) {
      for (const pair of pairs) {
        if (!pair || pair.length < 2) continue
        const [a, b] = pair
        if (!a || !b || a === b) continue
        let idx = roman.indexOf(a)
        while (idx >= 0) {
          const alt = roman.slice(0, idx) + b + roman.slice(idx + a.length)
          const c = cost + pairCost(a, b, costs)
          if (c >= (costs.intervocalic_invent || 8) && alt !== lower) {
            idx = roman.indexOf(a, idx + 1)
            continue
          }
          const prev = next.get(alt)
          if (prev == null || c < prev) next.set(alt, c)
          idx = roman.indexOf(a, idx + 1)
        }
      }
    }
    const ranked = [...next.entries()]
      .map(([roman, cost]) => ({ roman, cost }))
      .sort((x, y) => x.cost - y.cost || x.roman.length - y.roman.length || (x.roman < y.roman ? -1 : 1))
      .slice(0, beam)
    frontier = new Map(ranked.map((r) => [r.roman, r.cost]))
  }

  return [...frontier.entries()]
    .map(([roman, cost]) => ({ roman, cost }))
    .sort((x, y) => x.cost - y.cost || x.roman.length - y.roman.length || (x.roman < y.roman ? -1 : 1))
    .slice(0, beam)
}

/**
 * Drop high-cost phonetic inventions lacking dictionary evidence.
 */
export function filterLatticeNatives(candidates, opts) {
  const maxCost = (opts && opts.maxUnattestedCost) || 6
  const out = []
  for (const c of candidates) {
    const cost = c.transformCost || 0
    const attested = !!(c.attested || c.uni || c.stem || (c.weight || 0) >= 100)
    if (!attested && cost >= maxCost) continue
    out.push(c)
  }
  return out.slice(0, Math.min(64, (opts && opts.beam) || 64))
}

// Gujarati transliteration and bounded production queries.
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

export function isIndependentVowelToken(token) {
  return VOWEL_INDEPENDENT[token] !== undefined
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
const PRODUCTIVE_CONJUNCTS = [
  // ya-phala (વ્ય, ક્ય, …) — past participles, passives
  'v|y', 'k|y', 'g|y', 'c|y', 'ch|y', 'j|y', 't|y', 'd|y', 'n|y', 'p|y', 'b|y',
  'm|y', 'r|y', 'l|y', 's|y', 'sh|y', 'h|y', 'T|y', 'D|y',
  // ra clusters
  'p|r', 't|r', 'k|r', 'g|r', 'd|r', 'b|r', 's|r', 'sh|y', 'sh|r', 'f|r', 'ph|r',
  // va clusters
  'k|v', 't|v', 'd|v', 's|v', 'n|v', 'dh|v',
  // misc common (doc §7)
  't|n', 's|n', 's|t', 's|k', 's|th', 'd|y', 't|th',
]

function conjunctKey(a, b) {
  return a + '|' + b
}

function conjunctPolicy(policy) {
  const configured = policy && Array.isArray(policy.conjunct_pairs)
    ? policy.conjunct_pairs
    : PRODUCTIVE_CONJUNCTS
  const experimental = policy && policy.experimental_families &&
    Array.isArray(policy.experimental_families.conjunct_virama)
    ? policy.experimental_families.conjunct_virama
    : []
  return new Set(configured.concat(experimental))
}

function shouldFormConjunct(leftTok, rightTok, conjuncts) {
  if (!leftTok || !rightTok) return false
  if (conjuncts.has(conjunctKey(leftTok, rightTok))) return true
  // already-atomic digraphs in CONSONANTS (ksh/gy/dv) are single tokens
  return false
}

export const ANUSVARA = '\u0A82'
const U_MATRA = '\u0AC1'
const UU_MATRA = '\u0AC2'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isGujaratiConsonantCodePoint(code) {
  return code >= 0x0A95 && code <= 0x0AB9 && code !== 0x0AB1 && code !== 0x0AB4
}

export function endsWithConsonantWithImplicitA(str) {
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

function transliterateTokens(tokens, policy) {
  let result = ''
  const conjuncts = conjunctPolicy(policy)

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
        shouldFormConjunct(token, nextToken, conjuncts)
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

export function transliterate(input, policy) {
  const tokens = tokenize(input)
  return transliterateTokens(tokens, policy)
}

/** Collapse non-canonical independent-vowel spellings before de-duplication.
 *
 * Distilled corpora contain sequences such as અા and matra+ઇ. Gujarati uses
 * the precomposed independent vowel in these positions; keeping both forms
 * wastes menu slots and can put the malformed spelling above the canonical one.
 */
export function normalizeGujaratiOrthography(text) {
  return String(text || '')
    .replace(/અા/g, 'આ')
    .replace(/([ાિીુૂેૈોૌ])ઇ/g, '$1ઈ')
}

/**
 * Apple/Google-style diphthong splits: roman `ai`/`ay`/`oi`/`ui`/`ei` often mean
 * independent ઈ/ઇ (કોઈ, જોઈ, થઈ) — not only matra ૈ / bare ી from i↔ii.
 * Constructs forms the matra transliterator cannot emit.
 */
function diphthongAlternateForms(roman, policy) {
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
      const prefixGu = prefix ? transliterate(prefix, policy) : ''
      const suffixGu = suffix ? transliterate(suffix, policy) : ''
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
export function phoneticFormsForRoman(roman, policy) {
  // Western digits stay Arabic (2.9 / 2026), never ૨.૯.
  if (/^\d+(\.\d*)?$/.test(roman) || /^\d*\.\d+$/.test(roman)) return [String(roman)]
  const out = []
  const seen = new Set()
  function add(g) {
    if (!g || g === roman || seen.has(g)) return
    seen.add(g)
    out.push(g)
  }
  const base = transliterate(roman, policy)
  add(base)
  add(withNasalFinalU(base))
  for (const g of diphthongAlternateForms(roman, policy)) {
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
export const CONFUSION_MAP = {
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

export const ENDING_VARIANTS = {
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
export function withEndingVariants(s, configuredVariants) {
  const variants = configuredVariants || ENDING_VARIANTS
  const out = new Set([s])
  for (const [from, tos] of Object.entries(variants)) {
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

/** One internal doubled vowel with a following consonant (swagat→swaagat).
 * Excludes final lengthening and diphthongs such as gai→gaai.
 */
export function isInternalVowelLengthExpansion(typed, expanded) {
  if (!typed || !expanded || expanded.length !== typed.length + 1) return false
  const vowels = new Set(['a', 'i', 'u', 'o'])
  for (let at = 1; at < expanded.length - 1; at += 1) {
    const ch = expanded[at]
    if (!vowels.has(ch) || expanded[at - 1] !== ch) continue
    const collapsed = expanded.slice(0, at) + expanded.slice(at + 1)
    const typedFolded = typed.replace(/w/g, 'v')
    const collapsedFolded = collapsed.replace(/w/g, 'v')
    if (collapsedFolded !== typedFolded) continue
    const next = expanded[at + 1]
    if (!vowels.has(next)) return true
  }
  return false
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

export function generateAlternateForms(input, policy) {
  const endings = (policy && policy.ending_variants) || ENDING_VARIANTS
  const confusions = (policy && policy.alternate_confusions) || CONFUSION_MAP
  const forms = new Set()
  forms.add(input)

  // Prioritize seed ending + vowel-length + one-step confusions before deep recursion
  for (const ended of withEndingVariants(input, endings)) forms.add(ended)
  for (const mid of withMidVowelVariants(input)) forms.add(mid)
  for (const lead of withLeadingVowelVariants(input)) forms.add(lead)
  for (const trail of withTrailingSchwa(input)) forms.add(trail)
  for (const ret of withRetroflexNasal(input)) forms.add(ret)
  for (const nas of withAnusvaraNasals(input)) forms.add(nas)
  for (const gem of withGeminates(input)) forms.add(gem)
  for (const loan of withLoanDigraphs(input)) forms.add(loan)
  const keysFirst = Object.keys(confusions).sort((a, b) => b.length - a.length)
  for (const from of keysFirst) {
    for (const to of confusions[from]) {
      for (const replaced of applyConfusionOnce(input, from, to)) {
        forms.add(replaced)
        for (const ended of withEndingVariants(replaced, endings)) forms.add(ended)
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

    const keys = Object.keys(confusions).sort((a, b) => b.length - a.length)
    for (const from of keys) {
      const tos = confusions[from]
      for (const to of tos) {
        for (const replaced of applyConfusionOnce(s, from, to)) {
          if (forms.size < MAX_ALT_FORMS && !forms.has(replaced)) {
            forms.add(replaced)
            expand(replaced, depth + 1)
          }
        }
      }
    }

    for (const ended of withEndingVariants(s, endings)) {
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
  for (const ended of withEndingVariants(input, endings)) forms.add(ended)
  for (const mid of withMidVowelVariants(input)) forms.add(mid)
  for (const lead of withLeadingVowelVariants(input)) {
    forms.add(lead)
    for (const ended of withEndingVariants(lead, endings)) forms.add(ended)
    for (const mid of withMidVowelVariants(lead)) forms.add(mid)
  }
  for (const ret of withRetroflexNasal(input)) {
    forms.add(ret)
    for (const ended of withEndingVariants(ret, endings)) forms.add(ended)
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
export function isNearExactRomanSuffix(suf, fullKey, typedLen) {
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
