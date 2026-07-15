/** Runtime surface required by the binary-storage and explicit-learning paths. */
export const RUNTIME_CAPABILITIES_MODULE = 1

function method(value, name) {
  return !!value && typeof value[name] === 'function'
}

export function probeRuntimeCapabilities(env) {
  const ctx = env && env.engine && env.engine.context
  const segment = ctx && ctx.lastSegment
  let trie = null
  try {
    if (typeof globalThis.Trie === 'function') trie = new globalThis.Trie()
  } catch (_e) {}
  let neuralModel = false
  if (method(env, 'gujaratiModelAvailable')) {
    try {
      neuralModel = env.gujaratiModelAvailable() === true
    } catch (_e) {}
  } else {
    neuralModel =
      typeof globalThis.GujaratiModel !== 'undefined' &&
      method(globalThis.GujaratiModel, 'nbest')
  }
  return {
    trie_constructor: typeof globalThis.Trie === 'function',
    trie_find: method(trie, 'find'),
    trie_prefix_search: method(trie, 'prefixSearch'),
    write_file_atomic: method(env, 'writeFileAtomic'),
    segment_candidate_access:
      !segment || (method(segment, 'getCandidateAt') && Number.isFinite(Number(segment.candidateSize))),
    commit_notifier: !!ctx && !!ctx.commitNotifier && method(ctx.commitNotifier, 'connect'),
    neural_model: neuralModel,
  }
}

export function missingRuntimeCapabilities(capabilities, options) {
  const required = ['trie_constructor', 'trie_find', 'trie_prefix_search']
  if (options && options.learning) {
    required.push('write_file_atomic', 'segment_candidate_access', 'commit_notifier')
  }
  if (options && options.neural) required.push('neural_model')
  return required.filter((name) => !capabilities[name])
}

export function logRuntimeCapabilities(env) {
  const capabilities = probeRuntimeCapabilities(env)
  const active = Object.entries(capabilities)
    .filter((entry) => entry[1])
    .map((entry) => entry[0])
    .join(',')
  console.log('$qjs$ runtime capabilities active=' + active)
  return capabilities
}
