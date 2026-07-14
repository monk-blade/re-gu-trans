/**
 * Observe numbered selections before Rime's selector and confirm them on commit.
 * The pinned librime-qjs API exposes candidates through Context.lastSegment.
 */
import {
  EXPLICIT_PROMOTION_THRESHOLD,
  checkLearningCapability,
  explicitCount,
  initLearningSession,
  normalizeRoman,
  recordExplicitSelectionForSession,
} from './learning.js'

const PENDING_TTL_MS = 2000

const PENDING = {
  active: false,
  roman: '',
  candidateText: '',
  candidateType: '',
  candidateIndex: -1,
  compositionId: '',
  at: 0,
}

function clearPending() {
  PENDING.active = false
  PENDING.roman = ''
  PENDING.candidateText = ''
  PENDING.candidateType = ''
  PENDING.candidateIndex = -1
  PENDING.compositionId = ''
  PENDING.at = 0
}

function selectedNumber(keyEvent) {
  if (!keyEvent || keyEvent.release || keyEvent.ctrl || keyEvent.alt || keyEvent.shift) return 0
  const repr = String(keyEvent.repr || '')
  if (/^[1-9]$/.test(repr)) return Number(repr)
  const keypad = /^KP_([1-9])$/i.exec(repr)
  return keypad ? Number(keypad[1]) : 0
}

function isGujaratiCandidate(candidate) {
  if (!candidate) return false
  const text = String(candidate.text || '')
  const type = String(candidate.type || '').toLowerCase()
  if (!/[\u0A80-\u0AFF]/.test(text)) return false
  if (/[\u{1F300}-\u{1FAFF}]/u.test(text)) return false
  return !type.includes('latin') && !type.includes('emoji') && !type.includes('prefix')
}

function compositionRoman(ctx) {
  return normalizeRoman(ctx && ctx.input)
}

function compositionId(ctx, segment) {
  if (!ctx || !segment) return ''
  return compositionRoman(ctx) + '#' + Number(segment.start || 0) + ':' + Number(segment.end || 0)
}

function expireChangedComposition(ctx) {
  if (!PENDING.active) return false
  const current = compositionId(ctx, ctx && ctx.lastSegment)
  if (!current || current !== PENDING.compositionId) {
    clearPending()
    return true
  }
  return false
}

function committedText(ctx) {
  try {
    const last = ctx && ctx.commitHistory && ctx.commitHistory.last
    if (last && last.text) return String(last.text)
  } catch (_e) {}
  try {
    if (ctx && typeof ctx.getCommitText === 'function') return String(ctx.getCommitText() || '')
  } catch (_e) {}
  return ''
}

export function captureNumberedSelection(keyEvent, env, nowMs) {
  const number = selectedNumber(keyEvent)
  if (!number) return false
  const engine = env && env.engine
  const ctx = engine && engine.context
  const segment = ctx && ctx.lastSegment
  const pageSize = Math.max(1, Number(engine && engine.schema && engine.schema.pageSize) || 6)
  if (!ctx || typeof ctx.hasMenu !== 'function' || !ctx.hasMenu() || !segment) {
    clearPending()
    return false
  }
  const roman = compositionRoman(ctx)
  if (!roman) {
    clearPending()
    return false
  }
  const selectedIndex = Math.max(0, Number(segment.selectedIndex) || 0)
  const pageStart = Math.floor(selectedIndex / pageSize) * pageSize
  const candidateIndex = pageStart + number - 1
  const candidateSize = Math.max(0, Number(segment.candidateSize) || 0)
  if (number > pageSize || candidateIndex < 0 || candidateIndex >= candidateSize) {
    clearPending()
    return false
  }
  let candidate = null
  try {
    candidate = segment.getCandidateAt(candidateIndex)
  } catch (_e) {}
  if (!isGujaratiCandidate(candidate)) {
    clearPending()
    return false
  }
  PENDING.active = true
  PENDING.roman = roman
  PENDING.candidateText = String(candidate.text)
  PENDING.candidateType = String(candidate.type || '')
  PENDING.candidateIndex = candidateIndex
  PENDING.compositionId = compositionId(ctx, segment)
  PENDING.at = Number(nowMs) || Date.now()
  return true
}

export function confirmPendingSelection(env, notifiedContext, nowMs) {
  if (!PENDING.active) return false
  const now = Number(nowMs) || Date.now()
  if (now - PENDING.at > PENDING_TTL_MS) {
    clearPending()
    return false
  }
  const text = committedText(notifiedContext)
  if (!text || text !== PENDING.candidateText) {
    clearPending()
    return false
  }
  const roman = PENDING.roman
  const native = PENDING.candidateText
  clearPending()
  const result = recordExplicitSelectionForSession(env, roman, native, now)
  if (!result.ok) return false
  console.log(
    '$qjs$ explicit select roman=' +
      roman +
      ' native=' +
      native +
      ' count=' +
      explicitCount(result.store, roman, native) +
      ' threshold=' +
      EXPLICIT_PROMOTION_THRESHOLD
  )
  return true
}

/** @implements {Processor} */
export class SelectionTrackerProcessor {
  constructor(env) {
    this._enabled = false
    this._connection = null
    try {
      const capability = checkLearningCapability(env)
      if (!capability.ok) return
      initLearningSession(env)
      const ctx = env && env.engine && env.engine.context
      if (!ctx || !ctx.commitNotifier || typeof ctx.commitNotifier.connect !== 'function') {
        console.log('$qjs$ learning disabled: Context.commitNotifier.connect missing')
        return
      }
      this._connection = ctx.commitNotifier.connect((notifiedContext) => {
        confirmPendingSelection(env, notifiedContext)
      })
      this._enabled = true
      console.log('$qjs$ selection tracker ready threshold=' + EXPLICIT_PROMOTION_THRESHOLD)
    } catch (e) {
      console.log('$qjs$ selection_tracker init: ' + (e && e.message))
    }
  }

  finalizer() {
    clearPending()
    try {
      if (this._connection && typeof this._connection.disconnect === 'function') {
        this._connection.disconnect()
      }
    } catch (_e) {}
    this._connection = null
  }

  process(keyEvent, env) {
    try {
      if (!this._enabled) return 'kNoop'
      const ctx = env && env.engine && env.engine.context
      expireChangedComposition(ctx)
      const repr = String((keyEvent && keyEvent.repr) || '')
      if (!selectedNumber(keyEvent)) {
        if (/^(Escape|BackSpace)$/i.test(repr)) clearPending()
        return 'kNoop'
      }
      captureNumberedSelection(keyEvent, env)
      return 'kNoop'
    } catch (e) {
      clearPending()
      console.log('$qjs$ selection_tracker error: ' + (e && e.message))
      return 'kNoop'
    }
  }
}

export function peekPendingSelection() {
  return Object.assign({}, PENDING)
}

export function resetPendingSelectionForTests() {
  clearPending()
}
