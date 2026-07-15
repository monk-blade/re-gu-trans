#!/usr/bin/env node
/** Execute the production GujaratiTranslator with text or Trie-shaped storage. */
import fs from 'node:fs'
import path from 'node:path'
import { performance } from 'node:perf_hooks'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const JS = path.join(ROOT, 'rime', 'js')
const [mode = 'text', inputPath, outputPath, limitArg] = process.argv.slice(2)
if (!inputPath || !outputPath || !['text', 'trie'].includes(mode)) {
  throw new Error('usage: js_production_runner.mjs text|trie INPUT.jsonl OUTPUT.jsonl')
}
const neuralFixtures = process.env.NEURAL_FIXTURES
  ? new Map(Object.entries(JSON.parse(fs.readFileSync(process.env.NEURAL_FIXTURES, 'utf8'))))
  : null

class CandidateMock {
  constructor(type, start, end, text, comment, quality = 0) {
    this.type = type
    this.start = start
    this.end = end
    this.text = text
    this.comment = comment
    this.quality = quality
    this.preedit = ''
  }
}
globalThis.Candidate = CandidateMock

class FileBackedTrie {
  constructor() {
    this.map = new Map()
    this.sortedKeys = []
  }

  loadBinaryFile(binaryPath) {
    const name = path.basename(binaryPath)
    if (name === 'lexicon.trie.bin') {
      this.#loadUnique(path.join(JS, 'lexicon.trie.txt'))
    } else if (name === 'native_lm.trie.bin') {
      this.#loadUnique(path.join(JS, 'native_lm.tsv'))
    } else if (name === 'prefix.trie.bin') {
      const groups = new Map()
      for (const line of fs.readFileSync(path.join(JS, 'prefix.trie.txt'), 'utf8').split('\n')) {
        if (!line) continue
        const tab = line.indexOf('\t')
        if (tab < 1) continue
        const key = line.slice(0, tab)
        const payload = line.slice(tab + 1)
        const values = groups.get(key) || []
        values.push(payload)
        groups.set(key, values)
      }
      for (const [key, values] of groups.entries()) this.map.set(key, values.join('\x1e'))
    } else {
      throw new Error('unknown binary Trie path ' + binaryPath)
    }
    this.sortedKeys = Array.from(this.map.keys()).sort()
  }

  #loadUnique(file) {
    for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
      if (!line) continue
      const tab = line.indexOf('\t')
      if (tab < 1) continue
      this.map.set(line.slice(0, tab), line.slice(tab + 1))
    }
  }

  find(key) {
    return this.map.has(key) ? this.map.get(key) : null
  }

  prefixSearch(prefix) {
    const rows = []
    let low = 0
    let high = this.sortedKeys.length
    while (low < high) {
      const middle = (low + high) >> 1
      if (this.sortedKeys[middle] < prefix) low = middle + 1
      else high = middle
    }
    for (let index = low; index < this.sortedKeys.length; index += 1) {
      const text = this.sortedKeys[index]
      if (!text.startsWith(prefix)) break
      rows.push({ text, info: this.map.get(text) })
    }
    return rows
  }
}

if (mode === 'trie') globalThis.Trie = FileBackedTrie

const { GujaratiTranslator } = await import('../rime/js/engine.js')

const config = {
  getBool(key) {
    if (key === 'translator/debug_rank') return process.env.DEBUG_RANK === '1'
    if (key === 'translator/allow_text_fallback') return mode === 'text'
    if (key === 'translator/enable_user_learning') return false
    return null
  },
  getDouble() { return null },
  getString(key) {
    if (key === 'translator/neural_mode') return neuralFixtures ? 'auto' : 'off'
    return null
  },
}
const context = {
  input: '',
  commitHistory: { last: null },
  updateNotifier: { connect() { return { disconnect() {} } } },
  commitNotifier: { connect() { return { disconnect() {} } } },
  hasMenu() { return false },
}
const env = {
  userDataDir: path.join(ROOT, 'rime'),
  engine: { schema: { config, pageSize: 6 }, context },
  loadFile(file) {
    try {
      const text = fs.readFileSync(file, 'utf8')
      if (path.basename(file) !== 'ranking_policy.json' || !process.env.AKSHAR_DISABLE_FAMILY) {
        return text
      }
      const policy = JSON.parse(text)
      if (policy.experimental_families) {
        delete policy.experimental_families[process.env.AKSHAR_DISABLE_FAMILY]
      }
      return JSON.stringify(policy)
    } catch { return '' }
  },
}
if (neuralFixtures) {
  env.transliterateNBest = (roman, count) =>
    (neuralFixtures.get(String(roman).toLowerCase()) || []).slice(0, count)
}
const startupStarted = performance.now()
const translator = new GujaratiTranslator(env)
const startupMs = performance.now() - startupStarted
const limit = Math.max(0, Number(limitArg) || 0)
let rows = fs.readFileSync(inputPath, 'utf8').split('\n').filter(Boolean).map(JSON.parse)
if (limit) rows = rows.slice(0, limit)
const output = []
const queryTimes = []
for (const row of rows) {
  const roman = String(row.roman || row.input || '')
  context.input = roman
  const segment = { start: 0, end: roman.length }
  const queryStarted = performance.now()
  const candidates = translator.translate(roman, segment, env)
  queryTimes.push(performance.now() - queryStarted)
  const top6 = candidates.slice(0, 6).map((candidate) => String(candidate.text || ''))
  const finite = candidates.every(
    (candidate) => Number.isFinite(Number(candidate.quality))
  )
  const result = { roman, top6, finite }
  if (process.env.DEBUG_RANK === '1') {
    result.debug = candidates.slice(0, 6).map((candidate) => ({
      text: String(candidate.text || ''),
      ...(candidate.debugRank || {}),
    }))
  }
  output.push(result)
}
translator.finalizer()
fs.writeFileSync(outputPath, output.map((row) => JSON.stringify(row)).join('\n') + '\n')
const sortedTimes = [...queryTimes].sort((a, b) => a - b)
const percentile = (p) => sortedTimes.length
  ? sortedTimes[Math.min(sortedTimes.length - 1, Math.floor(sortedTimes.length * p))]
  : 0
console.log(JSON.stringify({
  mode,
  cases: output.length,
  finite: output.every((row) => row.finite),
  startup_ms: Number(startupMs.toFixed(3)),
  query_p50_ms: Number(percentile(0.5).toFixed(3)),
  query_p95_ms: Number(percentile(0.95).toFixed(3)),
  heap_mb: Number((process.memoryUsage().heapUsed / (1024 * 1024)).toFixed(3)),
}))
