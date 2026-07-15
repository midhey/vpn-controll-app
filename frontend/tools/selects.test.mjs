import assert from 'node:assert/strict'
import { readFile, readdir } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const sourceRoot = path.join(root, 'src')
const selectComponent = path.join(sourceRoot, 'shared/ui/BaseSelect.vue')

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

test('native selects are centralized in BaseSelect', async () => {
  const files = await vueFiles(sourceRoot)
  const offenders = []

  for (const file of files) {
    if (file === selectComponent) continue
    const source = await readFile(file, 'utf8')
    if (/<select\b/.test(source)) offenders.push(path.relative(root, file))
  }

  assert.deepEqual(offenders, [])
})

test('BaseSelect preserves the responsive and accessible control contracts', async () => {
  const source = await readFile(selectComponent, 'utf8')

  assert.match(source, /matchMedia\('\(max-width: 760px\)'\)/)
  assert.match(source, /<select[\s\S]+:class="\{ 'is-form-proxy': !isMobile \}"[\s\S]+:name="name"/)
  assert.match(source, /:aria-hidden="!isMobile \|\| undefined"/)
  assert.match(source, /@invalid="handleInvalid"/)
  assert.match(source, /role="combobox"/)
  assert.match(source, /role="listbox"/)
  assert.match(source, /role="option"/)
  assert.match(source, /:aria-activedescendant="activeDescendant"/)
  assert.match(source, /case 'Escape':/)
  assert.match(source, /case 'ArrowDown':/)
  assert.match(source, /document\.addEventListener\('pointerdown', handleDocumentPointerDown\)/)
  assert.match(source, /defineModel<SelectValue>/)
})
