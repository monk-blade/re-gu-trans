// commit_on_punct_processor.js
// When a candidate menu is open, Space and common punctuation commit the
// selected candidate (macOS TransliterationIM-style), then insert the mark.
//
// NOTE: This processor must be listed BEFORE key_binder in the schema.
// Default Rime bindings remap period → Page_Down when has_menu.

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

      const punct = punctForKey(String(keyEvent.repr || ''))
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

/**
 * @param {string} repr
 * @returns {string|null}
 */
function punctForKey(repr) {
  const r = String(repr || '')
  const lower = r.toLowerCase()

  // Strip optional Release/Shift- prefixes some frontends include
  const bare = lower
    .replace(/^release\+/i, '')
    .replace(/^shift\+/i, '')
    .replace(/^control\+/i, '')
    .replace(/^alt\+/i, '')
    .replace(/^super\+/i, '')

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
