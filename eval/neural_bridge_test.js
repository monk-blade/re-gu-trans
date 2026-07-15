import assert from 'node:assert/strict'
import {
  isValidGujaratiModelOutput,
  isValidNeuralRomanInput,
  neuralCapability,
  neuralNBest,
} from '../rime/js/neural.js'

assert.equal(neuralCapability({}).available, false)
assert.deepEqual(neuralNBest({}, 'padi', 4, 'auto').candidates, [])
assert.equal(neuralNBest({}, 'padi', 4, 'required').requiredMissing, true)
assert.equal(isValidNeuralRomanInput('yas'), true)
assert.equal(isValidNeuralRomanInput("o'brien"), true)
for (const input of ['', '.', '3.', '--', 'a..b', 'ગુ', 'a b', 'https://x']) {
  assert.equal(isValidNeuralRomanInput(input), false, input)
}
for (const native of ['યસ', 'પડી', 'ૐ', 'શ્રદ્ધા', 'હું']) {
  assert.equal(isValidGujaratiModelOutput(native), true, native)
}
for (const native of ['', 'ી', '્ય', 'ક્', 'ક્‍', 'કિી', 'અા', 'latin', 'બદલ�']) {
  assert.equal(isValidGujaratiModelOutput(native), false, native)
}
for (let index = 0; index < 5000; index += 1) {
  const invalid = index % 5 === 0
    ? `${index}.`
    : index % 5 === 1
      ? `word ${index}`
      : index % 5 === 2
        ? `a..b${index}`
        : index % 5 === 3
          ? `ગુજરાતી${index}`
          : `https://host${index}.example`
  assert.equal(isValidNeuralRomanInput(invalid), false, invalid)
}

let invalidCalls = 0
const invalidEnv = {
  transliterateNBest() {
    invalidCalls += 1
    return [{ native: 'ી', logProb: 0 }]
  },
}
assert.equal(neuralNBest(invalidEnv, '.', 4, 'auto').invalidInput, true)
assert.equal(invalidCalls, 0)

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
      { native: 'ી', logProb: -0.1 },
      { native: 'ક્', logProb: -0.1 },
    ]
  },
}
const result = neuralNBest(env, 'padi', 4, 'auto')
assert.deepEqual(result.candidates.map((item) => item.native), ['પડી', 'પાડી'])
assert.equal(result.capability.provider, 'environment')
console.log(JSON.stringify({ report: 'neural_bridge', ok: true, candidates: result.candidates.length }))
