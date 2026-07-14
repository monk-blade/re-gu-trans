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
