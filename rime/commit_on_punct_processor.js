// commit_on_punct_processor.js
// When a candidate menu is open, Space and common punctuation commit the
// selected candidate (macOS TransliterationIM-style), then insert the mark.
//
// NOTE: This processor must be listed BEFORE key_binder in the schema.
// Default Rime bindings remap period → Page_Down when has_menu.
// User LM is updated here on commit only (not on every translate keystroke).

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

      const committed = selectedCandidateText(ctx)

      if (typeof ctx.commit === 'function') {
        ctx.commit()
      }

      if (committed) {
        learnUserWord(env, committed)
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

function selectedCandidateText(ctx) {
  try {
    if (typeof ctx.getSelectedCandidate === 'function') {
      const sel = ctx.getSelectedCandidate()
      if (sel && sel.text) return String(sel.text)
    }
  } catch (_e) {}
  return ''
}

function resolveUserPath(path) {
  if (!path || typeof path !== 'string') return path
  if (path.startsWith('~/') && typeof os !== 'undefined' && os.homedir) {
    return os.homedir() + path.slice(1)
  }
  return path
}

function getEnvBool(env, key, fallback) {
  try {
    if (env && typeof env.engine && env.engine.schema) {
      const conf = env.engine.schema.config
      if (conf && typeof conf.getBool === 'function') {
        const v = conf.getBool(key)
        if (typeof v === 'boolean') return v
      }
    }
  } catch (_e) {}
  return fallback
}

/** Append-only personalization on commit (same TSV shape as translator user LM). */
function learnUserWord(env, word) {
  try {
    if (!getEnvBool(env, 'translator/enable_user_lm', true)) return
    if (!word || typeof word !== 'string') return
    const path = resolveUserPath('~/Library/Rime/gujarati.user.tsv')
    let text = ''
    try {
      if (typeof std !== 'undefined' && std.open) {
        const f = std.open(path, 'r')
        if (f) {
          text = f.readAsString() || ''
          f.close()
        }
      } else if (typeof read === 'function') {
        text = read(path) || ''
      }
    } catch (_e) {
      text = ''
    }
    const wordCounts = new Map()
    const bigramCounts = new Map()
    for (const line of String(text).split(/\r?\n/)) {
      if (!line) continue
      const parts = line.split('\t')
      if (parts.length === 2) {
        const w = parts[0]
        const c = Number(parts[1])
        if (w && Number.isFinite(c)) wordCounts.set(w, c)
      } else if (parts.length >= 3) {
        const prev = parts[0]
        const w = parts[1]
        const c = Number(parts[2])
        if (prev && w && Number.isFinite(c)) bigramCounts.set(prev + '|' + w, c)
      }
    }
    wordCounts.set(word, (wordCounts.get(word) || 0) + 1)
    const lines = []
    for (const [w, c] of wordCounts) lines.push(w + '\t' + c)
    for (const [k, c] of bigramCounts) {
      const idx = k.indexOf('|')
      if (idx < 0) continue
      lines.push(k.slice(0, idx) + '\t' + k.slice(idx + 1) + '\t' + c)
    }
    const out = lines.join('\n') + (lines.length ? '\n' : '')
    try {
      if (typeof write === 'function') {
        write(path, out)
      } else if (typeof std !== 'undefined' && std.open) {
        const f = std.open(path, 'w')
        if (f) {
          f.puts(out)
          f.close()
        }
      }
    } catch (e) {
      console.error('$qjs$ user lm write error:', e && e.message)
    }
  } catch (e) {
    console.error('$qjs$ learnUserWord error:', e && e.message)
  }
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
