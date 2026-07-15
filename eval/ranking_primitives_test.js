import assert from 'node:assert/strict'
import {
  TIER_DICT,
  TIER_EMOJI,
  TIER_PREFIX,
  layoutMenu,
  lexiconHitTier,
  makeCandidateRecord,
} from '../rime/js/ranking_primitives.js'
import { expandRomanLattice } from '../rime/js/phonetic.js'

assert.equal(lexiconHitTier('fuzzy', 800, 'ko', 'kau'), TIER_DICT)
const short = expandRomanLattice('ko', [['o', 'au']], {
  beam: 64,
  passes: 2,
  costs: { loan_o: 2.5 },
  length_budgets: { short: { beam: 16, passes: 1, max_cost: 2 } },
})
assert.deepEqual(short.map((item) => item.roman), ['ko'])

const record = makeCandidateRecord({ native: 'કો', typedRoman: 'ko', queryRoman: 'ko' })
assert.equal(record.transformCost, 0)
assert.deepEqual(record.provenance, [])

const gu = ['વાહ', 'વહ', 'વાઅહ', 'વાહન'].map((native, index) => makeCandidateRecord({ native, score: 100 - index }))
const emoji = makeCandidateRecord({ native: '🤩', source: 'emoji', tier: TIER_EMOJI, emojiConfidence: 0.98 })
const prefix = makeCandidateRecord({ native: 'વાહક', source: 'prefix', tier: TIER_PREFIX })
const menu = layoutMenu([...gu, prefix, emoji], {
  includeLatin: true,
  latinText: 'wah',
  maxGujaratiBeforeEmoji: 3,
  maxEmoji: 2,
  emojiMinConfidence: 0.9,
})
assert.deepEqual(menu.slice(0, 6).map((item) => item.native), ['વાહ', 'wah', 'વહ', 'વાઅહ', '🤩', 'વાહન'])
assert(menu.indexOf(emoji) < menu.indexOf(prefix))
console.log(JSON.stringify({ report: 'ranking_primitives', ok: true }))
