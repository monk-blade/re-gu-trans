/** Production-module smoke runner; no synthetic candidates. */
import { emptyLearning, recordExplicitSelection } from '../rime/js/learning.js'
import { layoutMenu, makeCandidateRecord, rankCandidates, TIER_DICT } from '../rime/js/ranking.js'

const learning = emptyLearning()
recordExplicitSelection(learning, 'padi', 'પડી', 1)
recordExplicitSelection(learning, 'padi', 'પડી', 2)
recordExplicitSelection(learning, 'padi', 'પડી', 3)
const records = [
  makeCandidateRecord({ native: 'પાડી', text: 'પાડી', tier: TIER_DICT, score: 10 }),
  makeCandidateRecord({ native: 'પડી', text: 'પડી', tier: TIER_DICT, score: 5 }),
]
const ranked = rankCandidates(records, { roman: 'padi' }, {}, learning)
const menu = layoutMenu(ranked, { includeLatin: true, latinText: 'padi' })
if (menu[0].native !== 'પડી' || menu[1].native !== 'padi') {
  throw new Error('production ranking/layout smoke failed')
}
console.log(JSON.stringify({ ok: true, production_modules: true, menu: menu.map((row) => row.native) }))
