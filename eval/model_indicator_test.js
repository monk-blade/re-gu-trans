import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const runner = path.join(root, 'eval', 'js_production_runner.mjs')
const policyPath = path.join(root, 'rime', 'js', 'ranking_policy.json')
const tempRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'akshar-model-indicator-'))

function runOnce() {
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
  return JSON.parse(fs.readFileSync(output, 'utf8').trim())
}

const originalPolicy = fs.readFileSync(policyPath, 'utf8')
try {
  // Markers are disabled by default (menu clutter feedback); verify that.
  const defaultRow = runOnce()
  assert.ok(defaultRow.top6.every((text) => !text.includes('🤖') && !text.includes('↪')))
  assert.ok(
    defaultRow.comments.every((item) => !item.comment.includes('🤖') && !item.comment.includes('↪')),
    'model indicator markers must be off by default'
  )

  // The feature itself must still work when a user opts back in.
  const policy = JSON.parse(originalPolicy)
  policy.model_indicator = { ...(policy.model_indicator || {}), enabled: true }
  fs.writeFileSync(policyPath, JSON.stringify(policy, null, 2) + '\n', 'utf8')
  const enabledRow = runOnce()
  assert.ok(enabledRow.top6.every((text) => !text.includes('🤖') && !text.includes('↪')))
  assert.ok(
    enabledRow.comments.some((item) => item.text === 'પડી' && item.comment.includes('🤖')),
    'opted-in model indicator must mark the neural-backed candidate'
  )
  assert.ok(enabledRow.comments.some((item) => item.comment.includes('↪')))
  assert.equal(enabledRow.comments.find((item) => item.text === 'padi').comment, '')

  console.log(JSON.stringify({ report: 'model_indicator', ok: true }))
} finally {
  fs.writeFileSync(policyPath, originalPolicy, 'utf8')
  fs.rmSync(tempRoot, { recursive: true, force: true })
}
