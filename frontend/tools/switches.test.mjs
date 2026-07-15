import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const sourceRoot = path.join(root, 'src')
const switchComponent = path.join(sourceRoot, 'shared/ui/BaseSwitch.vue')

async function vueFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = await Promise.all(
    entries.map((entry) => {
      const entryPath = path.join(directory, entry.name)
      if (entry.isDirectory()) return vueFiles(entryPath)
      return entry.name.endsWith('.vue') ? [entryPath] : []
    }),
  )
  return files.flat()
}

test('native checkbox inputs are centralized in BaseSwitch', async () => {
  const files = await vueFiles(sourceRoot)
  const offenders = []

  for (const file of files) {
    if (file === switchComponent) continue
    const source = await readFile(file, 'utf8')
    if (/type=["']checkbox["']/.test(source)) offenders.push(path.relative(root, file))
  }

  assert.deepEqual(offenders, [])
})

test('BaseSwitch keeps the native accessible input contract', async () => {
  const source = await readFile(switchComponent, 'utf8')

  assert.match(source, /<label[^>]+:for="inputId"/)
  assert.match(source, /<input[\s\S]+:id="inputId"[\s\S]+type="checkbox"/)
  assert.match(source, /role="switch"/)
  assert.match(source, /:disabled="disabled"/)
  assert.match(source, /\.switch__input:focus-visible \+ \.switch__control/)
})
