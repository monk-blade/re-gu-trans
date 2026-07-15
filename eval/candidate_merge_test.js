import assert from 'node:assert/strict'
import {
  makeCandidatePath,
  makeCandidateRecord,
  mergeCandidatePath,
  TIER_DICT,
} from '../rime/js/ranking_primitives.js'

const fuzzy = makeCandidatePath({
  source: 'fuzzy',
  queryRoman: 'ketlee',
  transformFamily: 'vowel_length',
  transformCost: 1,
  lexiconWeight: 75,
  tier: TIER_DICT,
  closeness: 900,
})
const neural = makeCandidatePath({
  source: 'neural',
  queryRoman: 'ketli',
  transformFamily: 'neural',
  tier: TIER_DICT,
  isNeural: true,
  neuralRank: 0,
  neuralRawLogProb: -0.42,
  neuralRelativeLogProb: 0,
  modelVersion: 'test-v2',
})

function aggregate(paths) {
  const record = makeCandidateRecord({ native: 'કેટલી', typedRoman: 'ketli' })
  for (const path of paths) mergeCandidatePath(record, path)
  return {
    source: record.source,
    provenance: record.provenance,
    weight: record.weight,
    transformCost: record.transformCost,
    tier: record.tier,
    neuralRank: record.neuralRank,
    neuralRelativeLogProb: record.neuralRelativeLogProb,
    modelCoreAgreement: record.modelCoreAgreement,
    paths: record.paths.length,
  }
}

assert.deepEqual(aggregate([fuzzy, neural]), aggregate([neural, fuzzy]))
assert.deepEqual(aggregate([fuzzy, neural, fuzzy, neural]), aggregate([neural, fuzzy]))
assert.deepEqual(aggregate([neural]), {
  source: 'neural',
  provenance: ['neural'],
  weight: 0,
  transformCost: 0,
  tier: TIER_DICT,
  neuralRank: 0,
  neuralRelativeLogProb: 0,
  modelCoreAgreement: false,
  paths: 1,
})
assert.equal(aggregate([fuzzy, neural]).modelCoreAgreement, true)
assert.equal(aggregate([fuzzy, neural]).weight, 75)
console.log(JSON.stringify({ report: 'candidate_merge', passed: true, permutations: 2 }))
