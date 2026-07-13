import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { writeAtomicIfChanged } from './lib/files.mjs';
import { findTokenViolations, normalizeTokenConfig } from './lib/tokens.mjs';

test('token checker allows token/theme colors and reports application literals', async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'frontend-kit-tokens-'));
  context.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, 'styles/tokens'), { recursive: true });
  await mkdir(path.join(root, 'styles/themes'), { recursive: true });
  await mkdir(path.join(root, 'styles/app'), { recursive: true });
  await mkdir(path.join(root, 'integrations/wordpress'), { recursive: true });
  await writeAtomicIfChanged(path.join(root, 'styles/tokens/_palette.scss'), ':root { --raw: #fff; }');
  await writeAtomicIfChanged(path.join(root, 'styles/themes/_dark.scss'), ':root { --bg: rgb(0 0 0); }');
  await writeAtomicIfChanged(
    path.join(root, 'styles/app/_card.scss'),
    '#face { color: #abcdef; background: rgba(0, 0, 0, 50%); }\n@include ring(hsl(0 0% 0%));',
  );
  await writeAtomicIfChanged(
    path.join(root, 'integrations/wordpress/_entry.scss'),
    '.wordpress { border-color: #123456; }',
  );

  const config = normalizeTokenConfig(
    {
      tokenCheck: {
        includeDirs: ['styles', 'integrations'],
        allowedDirs: ['styles/tokens', 'styles/themes'],
      },
    },
    root,
  );
  const violations = await findTokenViolations(config);

  assert.equal(violations.length, 4);
  assert.deepEqual(
    violations.map((violation) => violation.value),
    ['#123456', '#abcdef', 'rgba(', 'hsl('],
  );
  assert.ok(violations.some((violation) => violation.file.endsWith('_entry.scss')));
});
