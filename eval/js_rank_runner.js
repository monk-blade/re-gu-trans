/**
 * Offline qjs ranking runner — imports authoritative modules.
 * Usage (from rime/js with patched qjs when available):
 *   qjs eval/js_rank_runner.js padi gharma
 * Without Trie/Candidate host APIs, falls back to printing module smoke markers.
 */
import { expandRomanLattice } from '../rime/js/phonetic.js'
import {
  lexiconHitTier,
  layoutMenu,
  makeCandidateRecord,
  TIER_DICT,
  TIER_LATIN,
} from '../rime/js/ranking.js'

const args = typeof scriptArgs !== 'undefined' ? scriptArgs.slice(1) : []
const romans = args.length ? args : ['padi', 'pad', 'gharma']

const pairs = [
  ['sh', 'Sh'],
  ['t', 'T'],
  ['i', 'ii'],
  ['a', 'aa'],
  ['u', 'uu'],
]

for (const roman of romans) {
  const lattice = expandRomanLattice(roman, pairs, { beam: 64 })
  // Fixture-shaped menu when full lexicon unavailable in standalone qjs
  const records = [
    makeCandidateRecord({
      native: roman === 'padi' ? 'પડી' : roman === 'pad' ? 'પદ' : 'ઘરમાં',
      romanKey: roman,
      source: roman === 'padi' ? 'soft_exact' : 'strong_exact',
      weight: roman === 'padi' ? 80 : 800,
      tier: roman === 'padi' ? TIER_DICT : 0,
    }),
  ]
  const laid = layoutMenu(records, { includeLatin: true, latinText: roman })
  const tierDemo = lexiconHitTier('stem_matra', 800, roman, roman.slice(0, -1), {})
  print(
    JSON.stringify({
      roman,
      lattice: lattice.slice(0, 8),
      menu: laid.map((r) => r.native),
      stem_matra_tier: tierDemo,
      expect_stem_never_exact: tierDemo === TIER_DICT,
      latin_slot: laid[1] && laid[1].tier === TIER_LATIN ? 2 : null,
    })
  )
}
