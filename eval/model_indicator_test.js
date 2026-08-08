import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const runner = path.join(root, 'eval', 'js_production_runner.mjs')
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'akshar-model-indicator-'))
try {
  const input = path.join(tempRoot, 'input.jsonl')
  const output = path.join(tempRoot, 'output.jsonl')
  const fixtures = path.join(tempRoot, 'neural.json')
  fs.writeFileSync(input, '{"roman":"padi"}\n', 'utf8')
  fs.writeFileSync(
    fixtures,
    JSON.stringify({ padi: [{ native: 'પડી', logProb: 0, modelVersion: 'test' }] }),
    'utf8'
  )
  const processResult = spawnSync(
    process.execPath,
    [runner, 'text', input, output],
    {
      cwd: root,
      env: { ...process.env, INSPECT_COMMENTS: '1', NEURAL_FIXTURES: fixtures },
      encoding: 'utf8',
    }
  )
  assert.equal(processResult.status, 0, processResult.stdout + processResult.stderr)
  const row = JSON.parse(fs.readFileSync(output, 'utf8').trim())
  assert.ok(row.top6.every((text) => !text.includes('🤖') && !text.includes('↪')))
  assert.ok(row.comments.some((item) => item.text === 'પડી' && item.comment.includes('🤖')))
  assert.ok(row.comments.some((item) => item.comment.includes('↪')))
  assert.equal(row.comments.find((item) => item.text === 'padi').comment, '')
  console.log(JSON.stringify({ report: 'model_indicator', ok: true }))
} finally {
  fs.rmSync(tempRoot, { recursive: true, force: true })
}
