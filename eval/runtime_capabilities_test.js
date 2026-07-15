import {
  missingRuntimeCapabilities,
  probeRuntimeCapabilities,
} from '../rime/js/runtime_capabilities.js'

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

globalThis.Trie = class {
  find() {}
  prefixSearch() {}
}
const env = {
  writeFileAtomic() {},
  engine: {
    context: {
      lastSegment: { candidateSize: 1, getCandidateAt() {} },
      commitNotifier: { connect() {} },
    },
  },
}
const capabilities = probeRuntimeCapabilities(env)
assert(missingRuntimeCapabilities(capabilities, { learning: true }).length === 0, 'full runtime')
assert(missingRuntimeCapabilities(capabilities, { neural: true }).includes('neural_model'), 'neural optional absent')
env.transliterateNBest = () => []
env.gujaratiModelAvailable = () => true
assert(missingRuntimeCapabilities(probeRuntimeCapabilities(env), { neural: true }).length === 0, 'neural bridge observed')
env.gujaratiModelAvailable = () => false
assert(
  missingRuntimeCapabilities(probeRuntimeCapabilities(env), { neural: true }).includes('neural_model'),
  'bridge without installed model is unavailable'
)
delete env.writeFileAtomic
assert(
  missingRuntimeCapabilities(probeRuntimeCapabilities(env), { learning: true }).includes('write_file_atomic'),
  'writer required for learning'
)
console.log(JSON.stringify({ ok: true, production_js: true }))
