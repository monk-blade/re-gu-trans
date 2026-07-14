#!/usr/bin/env node
/** Exercise numbered-selection promotion through the production translator. */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

class CandidateMock {
  constructor(type, start, end, text, comment, quality = 0) {
    Object.assign(this, { type, start, end, text, comment, quality, preedit: '' })
  }
}
globalThis.Candidate = CandidateMock

const { GujaratiTranslator } = await import('../rime/js/engine.js')
const { SelectionTrackerProcessor } = await import('../rime/js/selection_tracker_processor.js')
const { resetLearningSessionForTests } = await import('../rime/js/learning.js')

let persisted = ''
let notifier = null
const config = {
  getBool(key) {
    if (key === 'translator/allow_text_fallback') return true
    if (key === 'translator/enable_user_learning') return true
    return null
  },
  getDouble() { return null },
}
const context = {
  input: 'padi',
  lastSegment: null,
  commitHistory: { last: null },
  updateNotifier: { connect() { return { disconnect() {} } } },
  commitNotifier: {
    connect(callback) {
      notifier = callback
      return { disconnect() { notifier = null } }
    },
  },
  hasMenu() { return !!this.lastSegment },
}
const env = {
  userDataDir: path.join(ROOT, 'rime'),
  engine: { schema: { config, pageSize: 6 }, context },
  loadFile(file) {
    if (String(file).endsWith('gujarati.user-learning.json')) return persisted
    try { return fs.readFileSync(file, 'utf8') } catch { return '' }
  },
  writeFileAtomic(file, content) {
    if (file !== 'gujarati.user-learning.json') throw new Error('unexpected learning path')
    persisted = content
  },
}

function menu(translator) {
  context.input = 'padi'
  const candidates = translator.translate('padi', { start: 0, end: 4 }, env)
  context.lastSegment = {
    start: 0,
    end: 4,
    selectedIndex: 0,
    candidateSize: candidates.length,
    getCandidateAt(index) { return candidates[index] || null },
  }
  return candidates
}

resetLearningSessionForTests()
const translator = new GujaratiTranslator(env)
const tracker = new SelectionTrackerProcessor(env)
const initial = menu(translator)
const target = 'પાડી'
const initialIndex = initial.findIndex((candidate) => candidate.text === target)
if (initialIndex < 0 || initialIndex >= 9) throw new Error('target candidate unavailable numerically')

const snapshots = []
for (let selection = 1; selection <= 3; selection += 1) {
  const candidates = menu(translator)
  const index = candidates.findIndex((candidate) => candidate.text === target)
  context.lastSegment.selectedIndex = index
  tracker.process({ repr: String(index + 1), release: false }, env)
  context.commitHistory.last = { text: target, type: 'thru' }
  notifier(context)
  const next = menu(translator).map((candidate) => candidate.text)
  snapshots.push({ selection, top: next[0], menu: next.slice(0, 6) })
}

const learned = JSON.parse(persisted)
const preferred = learned.choices.padi.preferred_native
const count = learned.choices.padi.natives[target].explicit_count
const ok =
  snapshots[0].top !== target &&
  snapshots[1].top !== target &&
  snapshots[2].top === target &&
  snapshots[2].menu[1] === 'padi' &&
  preferred === target &&
  count === 3

tracker.finalizer()
translator.finalizer()
const report = { ok, target, initial_index: initialIndex, count, preferred, snapshots }
fs.writeFileSync(
  path.join(ROOT, 'eval', 'learning_integration_summary.json'),
  JSON.stringify(report, null, 2) + '\n'
)
console.log(JSON.stringify(report))
if (!ok) process.exit(1)
