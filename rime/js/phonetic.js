/**
 * Phonetic / fuzzy generation + weighted lattice (beam ≤ 64).
 */
export const PHONETIC_MODULE = 2

export const DEFAULT_LATTICE = {
  beam: 64,
  costs: {
    typed: 0,
    vowel_length: 1,
    case_place: 1.5,
    dental_retroflex: 2,
    aspirate: 2.5,
    digraph: 2,
    intervocalic_invent: 8,
  },
}

/**
 * Beam-search roman transforms using confusion pairs + costs.
 * Returns [{roman, cost}] sorted by cost, capped at beam.
 */
export function expandRomanLattice(typed, confusionPairs, latticePolicy) {
  const policy = Object.assign({}, DEFAULT_LATTICE, latticePolicy || {})
  const costs = Object.assign({}, DEFAULT_LATTICE.costs, policy.costs || {})
  const beam = Math.min(64, Math.max(1, policy.beam || 64))
  const lower = String(typed || '').toLowerCase()
  if (!lower) return []

  const pairs = confusionPairs || []
  /** @type {Map<string, number>} */
  let frontier = new Map([[lower, costs.typed]])

  // One expansion pass over confusion pairs (cheap lattice)
  const next = new Map(frontier)
  for (const [roman, cost] of frontier) {
    for (const pair of pairs) {
      if (!pair || pair.length < 2) continue
      const [a, b] = pair
      if (!a || !b || a === b) continue
      let idx = roman.indexOf(a)
      while (idx >= 0) {
        const alt = roman.slice(0, idx) + b + roman.slice(idx + a.length)
        let c = cost
        if (a.length !== b.length) c += costs.vowel_length
        else if (/[TDNL]/.test(a + b)) c += costs.dental_retroflex
        else if (/h/i.test(a + b)) c += costs.aspirate
        else c += costs.digraph
        const prev = next.get(alt)
        if (prev == null || c < prev) next.set(alt, c)
        idx = roman.indexOf(a, idx + 1)
      }
    }
  }

  const ranked = [...next.entries()]
    .map(([roman, cost]) => ({ roman, cost }))
    .sort((x, y) => x.cost - y.cost || x.roman.length - y.roman.length || (x.roman < y.roman ? -1 : 1))
  return ranked.slice(0, beam)
}

/**
 * Drop high-cost phonetic inventions lacking dictionary evidence.
 */
export function filterLatticeNatives(candidates, opts) {
  const maxCost = (opts && opts.maxUnattestedCost) || 6
  const out = []
  for (const c of candidates) {
    const cost = c.transformCost || 0
    const attested = !!(c.attested || c.uni || c.stem)
    if (!attested && cost >= maxCost) continue
    out.push(c)
  }
  return out.slice(0, Math.min(64, (opts && opts.beam) || 64))
}
