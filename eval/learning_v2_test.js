import {
  emptyLearning,
  explicitCount,
  migrateLearning,
  parseLearning,
  preferredNative,
  recordExplicitSelection,
  resetLearningSessionForTests,
} from '../rime/js/learning.js'
import {
  SelectionTrackerProcessor,
  peekPendingSelection,
  resetPendingSelectionForTests,
} from '../rime/js/selection_tracker_processor.js'

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) throw new Error(message + ': expected=' + expected + ' actual=' + actual)
}

const migrated = migrateLearning({
  version: 1,
  choices: { 'Pa Di!': { 'પાડી': { count: 9, last_used: 1 } } },
})
assertEqual(preferredNative(migrated, 'padi'), null, 'v1 must not promote')
assertEqual(explicitCount(migrated, 'padi', 'પાડી'), 0, 'v1 explicit count')
assertEqual(migrated.choices.padi.natives['પાડી'].legacy_count, 9, 'v1 legacy count')
assertEqual(Object.keys(parseLearning('{broken').choices).length, 0, 'corrupt JSON fallback')

let direct = emptyLearning()
recordExplicitSelection(direct, 'PADI', 'પડી', 1)
recordExplicitSelection(direct, 'padi', 'પડી', 2)
assertEqual(preferredNative(direct, 'padi'), null, 'two selections do not promote')
recordExplicitSelection(direct, 'padi', 'પડી', 3)
assertEqual(preferredNative(direct, 'padi'), 'પડી', 'third selection promotes')
recordExplicitSelection(direct, 'padi', 'પાડી', 4)
recordExplicitSelection(direct, 'padi', 'પાડી', 5)
recordExplicitSelection(direct, 'padi', 'પાડી', 6)
assertEqual(preferredNative(direct, 'padi'), 'પાડી', 'new third selection replaces preference')

function makeHarness(options) {
  const state = { file: options && options.file ? options.file : '', callback: null, disconnected: false }
  const candidates = [
    { text: 'પડી', type: 'exact' },
    { text: 'padi', type: 'latin' },
    { text: 'પાડી', type: 'dict' },
    { text: '🙂', type: 'emoji' },
    { text: 'પડવું', type: 'prefix' },
  ]
  const segment = {
    start: 0,
    end: 4,
    selectedIndex: 0,
    candidateSize: candidates.length,
    getCandidateAt(index) {
      return candidates[index] || null
    },
  }
  const context = {
    input: 'padi',
    lastSegment: segment,
    commitHistory: { last: null },
    hasMenu() {
      return true
    },
    commitNotifier: {
      connect(callback) {
        state.callback = callback
        return { disconnect() { state.disconnected = true } }
      },
    },
  }
  const env = {
    userDataDir: '/mock-rime',
    engine: { context, schema: { pageSize: 6 } },
    loadFile(path) {
      return path.endsWith('gujarati.user-learning.json') ? state.file : ''
    },
    writeFileAtomic(path, content) {
      assertEqual(path, 'gujarati.user-learning.json', 'atomic relative path')
      state.file = content
    },
  }
  return { env, state, context, segment, candidates }
}

function selectAndCommit(harness, key, text) {
  harness.context.commitHistory.last = null
  const result = harness.processor.process(
    { repr: String(key), release: false, ctrl: false, alt: false, shift: false },
    harness.env
  )
  assertEqual(result, 'kNoop', 'tracker must leave selection to Rime')
  assert(peekPendingSelection().active, 'valid Gujarati selection must be pending')
  harness.context.commitHistory.last = { text, type: 'thru' }
  harness.state.callback(harness.context)
}

resetLearningSessionForTests()
resetPendingSelectionForTests()
const harness = makeHarness()
harness.processor = new SelectionTrackerProcessor(harness.env)
assert(harness.state.callback, 'commit notifier connected')

selectAndCommit(harness, 3, 'પાડી')
selectAndCommit(harness, 3, 'પાડી')
let stored = JSON.parse(harness.state.file)
assertEqual(stored.choices.padi.preferred_native, null, 'two numeric commits not preferred')
selectAndCommit(harness, 3, 'પાડી')
stored = JSON.parse(harness.state.file)
assertEqual(stored.choices.padi.preferred_native, 'પાડી', 'third numeric commit preferred')
assertEqual(stored.choices.padi.natives['પાડી'].explicit_count, 3, 'explicit count persisted')

// Page two: selectedIndex 2 with page size 2 means key 1 selects absolute index 2.
harness.env.engine.schema.pageSize = 2
harness.segment.selectedIndex = 2
selectAndCommit(harness, 1, 'પાડી')
assertEqual(peekPendingSelection().active, false, 'pending cleared after page-two commit')

// Latin/emoji/prefix/invalid numbers must never create a pending selection.
harness.segment.selectedIndex = 0
harness.env.engine.schema.pageSize = 6
for (const key of [2, 4, 5, 6]) {
  harness.processor.process(
    { repr: String(key), release: false, ctrl: false, alt: false, shift: false },
    harness.env
  )
  assertEqual(peekPendingSelection().active, false, 'disallowed candidate ignored key=' + key)
}

// Non-numeric commit keys and mouse commits cannot start explicit learning.
for (const repr of ['space', 'Return', 'period', 'comma']) {
  harness.processor.process(
    { repr, release: false, ctrl: false, alt: false, shift: false },
    harness.env
  )
  assertEqual(peekPendingSelection().active, false, 'non-numeric commit ignored repr=' + repr)
}
harness.state.callback(harness.context)
assertEqual(peekPendingSelection().active, false, 'mouse-style commit without pending ignored')

// Composition identity change cancels a previously captured numeric selection.
harness.segment.selectedIndex = 0
harness.processor.process(
  { repr: '1', release: false, ctrl: false, alt: false, shift: false },
  harness.env
)
assert(peekPendingSelection().active, 'Gujarati numeric selection captured')
harness.context.input = 'padii'
harness.processor.process({ repr: 'x', release: false }, harness.env)
assertEqual(peekPendingSelection().active, false, 'changed composition clears pending')
harness.context.input = 'padi'

harness.processor.finalizer()
assert(harness.state.disconnected, 'notifier disconnected')

// Missing atomic writer disables only the tracker and does not consume keys.
resetLearningSessionForTests()
const noWriter = makeHarness()
delete noWriter.env.writeFileAtomic
const disabled = new SelectionTrackerProcessor(noWriter.env)
assertEqual(
  disabled.process({ repr: '1', release: false }, noWriter.env),
  'kNoop',
  'disabled tracker must not break typing'
)

console.log(JSON.stringify({ ok: true, threshold: 3, production_js: true }))
