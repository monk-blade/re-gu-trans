// Minimal smoke-test translator for librime-qjs
export class GujaratiTranslator {
  constructor(env) {
    console.log('$qjs$ gujarati minimal init ns=' + (env && env.namespace))
  }

  finalizer() {
    console.log('$qjs$ gujarati minimal finit')
  }

  translate(input, segment, env) {
    if (!input) return []
    // Simple known mappings for smoke test
    const map = {
      kem: 'કેમ',
      kemcho: 'કેમ છો',
      aavjo: 'આવજો',
      gujarat: 'ગુજરાત',
      namaste: 'નમસ્તે',
      dhanyavad: 'ધન્યવાદ',
    }
    const key = String(input).toLowerCase()
    const text = map[key] || ('[' + input + ']')
    return [new Candidate('gujarati', segment.start, segment.end, text, input)]
  }
}
