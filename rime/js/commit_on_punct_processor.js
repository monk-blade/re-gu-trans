// commit_on_punct_processor.js
// When a candidate menu is open, Space and common punctuation commit the
// selected candidate (macOS TransliterationIM-style), then insert the mark.
//
// Digit / Return selection is handled by Rime selector + translator notifiers
// (user learning). This processor only handles unmodified commit punctuation.
// Control / Alt / Super / Command modifiers always pass through (kNoop).
//
// NOTE: Listed BEFORE key_binder so period is not remapped to Page_Down.

/**
 * @implements {Processor}
 */
export class CommitOnPunctProcessor {
  constructor(_env) {}

  finalizer() {}

  /**
   * @param {KeyEvent} keyEvent
   * @param {Environment} env
   * @returns {ProcessResult}
   */
  process(keyEvent, env) {
    try {
      if (!keyEvent || keyEvent.release) return 'kNoop'
      const repr = String(keyEvent.repr || '')
      if (hasModifier(repr)) return 'kNoop'

      const punct = punctForKey(repr)
      if (punct === null) return 'kNoop'

      const engine = env && env.engine
      const ctx = engine && engine.context
      if (!ctx || typeof ctx.hasMenu !== 'function' || !ctx.hasMenu()) {
        return 'kNoop'
      }

      if (typeof ctx.commit === 'function') {
        ctx.commit()
      }

      if (punct !== '' && engine && typeof engine.commitText === 'function') {
        engine.commitText(punct)
      }

      if (typeof ctx.clear === 'function') {
        ctx.clear()
      }
      return 'kAccepted'
    } catch (e) {
      console.error('$qjs$ commit_on_punct error:', e && e.message)
      return 'kNoop'
    }
  }
}

function hasModifier(repr) {
  const r = String(repr || '').toLowerCase()
  return (
    r.includes('control+') ||
    r.includes('ctrl+') ||
    r.includes('alt+') ||
    r.includes('option+') ||
    r.includes('super+') ||
    r.includes('meta+') ||
    r.includes('command+') ||
    r.includes('cmd+')
  )
}

/**
 * @param {string} repr
 * @returns {string|null}
 */
function punctForKey(repr) {
  const r = String(repr || '')
  const lower = r.toLowerCase()

  const bare = lower
    .replace(/^release\+/i, '')
    .replace(/^shift\+/i, '')

  if (bare === 'space' || r === ' ') return ' '

  const named = {
    period: '.',
    kp_decimal: '.',
    kp_period: '.',
    comma: ',',
    kp_separator: ',',
    semicolon: ';',
    apostrophe: "'",
    quotedbl: '"',
    slash: '/',
    backslash: '\\',
    minus: '-',
    kp_subtract: '-',
    equal: '=',
    grave: '`',
    bracketleft: '[',
    bracketright: ']',
    exclam: '!',
    question: '?',
    colon: ':',
    parenleft: '(',
    parenright: ')',
  }
  if (Object.prototype.hasOwnProperty.call(named, bare)) {
    return named[bare]
  }

  if (r.length === 1 && /[.,;:'"!?\/\\\-_=`[\]()]/.test(r)) {
    return r
  }
  if (bare.length === 1 && /[.,;:'"!?\/\\\-_=`[\]()]/.test(bare)) {
    return bare
  }

  return null
}
