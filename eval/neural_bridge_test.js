import assert from 'node:assert/strict'
import { neuralCapability, neuralNBest } from '../rime/js/neural.js'

assert.equal(neuralCapability({}).available, false)
assert.deepEqual(neuralNBest({}, 'padi', 4, 'auto').candidates, [])
assert.equal(neuralNBest({}, 'padi', 4, 'required').requiredMissing, true)

const env = {
  transliterateNBest(roman, limit) {
    assert.equal(roman, 'padi')
    assert.equal(limit, 4)
    return [
      { native: 'પડી', logProb: -0.1, modelVersion: 'test' },
      { native: 'પાડી', logProb: -0.3, modelVersion: 'test' },
      { native: 'latin', logProb: -0.01 },
      { native: 'પડી', logProb: -0.4 },
      { native: 'બદલ�', logProb: -0.2 },
    ]
  },
}
const result = neuralNBest(env, 'padi', 4, 'auto')
assert.deepEqual(result.candidates.map((item) => item.native), ['પડી', 'પાડી'])
assert.equal(result.capability.provider, 'environment')
console.log(JSON.stringify({ report: 'neural_bridge', ok: true, candidates: result.candidates.length }))
