// commit_on_punct_processor.js
// When a candidate menu is open, Space and common punctuation commit the
// selected candidate (macOS TransliterationIM-style), then insert the mark.

/**
 * @implements {Processor}
 */
export class CommitOnPunctProcessor {
  constructor(env) {
    // no-op
  }

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
      const punct = punctForKey(repr, keyEvent)
      if (punct === null) return 'kNoop'

      const engine = env && env.engine
      const ctx = engine && engine.context
      if (!ctx) return 'kNoop'

      // Only intercept when composing with a candidate menu
      const composing =
        (typeof ctx.isComposing === 'function' && ctx.isComposing()) ||
        (typeof ctx.hasMenu === 'function' && ctx.hasMenu()) ||
        (ctx.input && String(ctx.input).length > 0)
      if (!composing) return 'kNoop'
      if (typeof ctx.hasMenu === 'function' && !ctx.hasMenu()) {
        // Still composing but no menu — let default editors handle
        return 'kNoop'
      }

      const cand =
        (ctx.lastSegment && ctx.lastSegment.selectedCandidate) ||
        (typeof ctx.getSelectedCandidate === 'function' && ctx.getSelectedCandidate()) ||
        null
      // Commit composition (selected candidate or raw input)
      if (typeof ctx.commit === 'function') {
        ctx.commit()
      }

      // Append the punctuation / space after the committed word
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
 * Map key representation → text to insert after commit.
 * Returns null if this key should not trigger commit-on-punct.
 * Returns '' for keys that commit without appending (none currently).
 */
function punctForKey(repr, keyEvent) {
  const r = repr
  const lower = r.toLowerCase()

  // Space commits and inserts a space
  if (lower === 'space' || r === ' ') return ' '

  // Named keysyms (Rime / X11 style)
  const named = {
    period: '.',
    comma: ',',
    semicolon: ';',
    apostrophe: "'",
    quotedbl: '"',
    slash: '/',
    backslash: '\\',
    minus: '-',
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
  if (Object.prototype.hasOwnProperty.call(named, lower)) {
    return named[lower]
  }

  // Literal single-character punctuation (some frontends report these)
  if (r.length === 1 && /[.,;:'"!?\/\\\-_=`[\]()]/.test(r)) {
    return r
  }

  // Shift+digit punctuation on US layout sometimes arrives as the symbol
  if (r.length === 1 && /[!@#$%^&*]/.test(r)) {
    return r
  }

  return null
}
