import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import sharp from 'sharp';

import { assertImageMagic, normalizeImageConfig, runImagePipeline } from './lib/images.mjs';

test('image pipeline preserves paths, converts formats and skips unchanged outputs', async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'frontend-kit-images-'));
  context.after(() => rm(root, { recursive: true, force: true }));
  const sourceDir = path.join(root, 'source', 'nested');
  await mkdir(sourceDir, { recursive: true });
  const png = await sharp({
    create: { width: 8, height: 6, channels: 4, background: { r: 32, g: 64, b: 96, alpha: 1 } },
  })
    .png()
    .toBuffer();
  await import('./lib/files.mjs').then(({ writeAtomicIfChanged }) =>
    writeAtomicIfChanged(path.join(sourceDir, 'sample.png'), png),
  );

  const config = normalizeImageConfig(
    {
      images: {
        sourceDir: 'source',
        outputDir: 'output',
        manifest: 'cache/images.json',
        formats: ['avif', 'webp'],
        copyOriginals: true,
        quality: { webp: 80, avif: 50 },
        effort: { webp: 2, avif: 1 },
      },
    },
    root,
  );

  const first = await runImagePipeline(config);
  await import('./lib/files.mjs').then(({ writeAtomicIfChanged }) =>
    writeAtomicIfChanged(path.join(root, 'output/manual-note.txt'), 'keep'),
  );
  const second = await runImagePipeline(config, {
    converter: () => {
      throw new Error('Sharp converter must not run for cached outputs.');
    },
  });
  assert.deepEqual(first, {
    sourceCount: 1,
    rasterCount: 1,
    writtenFiles: 3,
    unchangedFiles: 0,
    prunedFiles: 0,
  });
  assert.deepEqual(second, {
    sourceCount: 1,
    rasterCount: 1,
    writtenFiles: 0,
    unchangedFiles: 3,
    prunedFiles: 0,
  });

  assert.equal(
    Buffer.compare(await readFile(path.join(root, 'output/nested/sample.png')), png),
    0,
  );
  assertImageMagic(await readFile(path.join(root, 'output/nested/sample.webp')), 'webp');
  assertImageMagic(await readFile(path.join(root, 'output/nested/sample.avif')), 'avif');

  await rm(path.join(sourceDir, 'sample.png'));
  assert.deepEqual(await runImagePipeline(config), {
    sourceCount: 0,
    rasterCount: 0,
    writtenFiles: 0,
    unchangedFiles: 0,
    prunedFiles: 3,
  });
  await assert.rejects(readFile(path.join(root, 'output/nested/sample.webp')), {
    code: 'ENOENT',
  });
  assert.equal(await readFile(path.join(root, 'output/manual-note.txt'), 'utf8'), 'keep');
});

test('empty image source directory succeeds', async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'frontend-kit-images-empty-'));
  context.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, 'source'));
  const config = normalizeImageConfig(
    {
      images: {
        sourceDir: 'source',
        outputDir: 'output',
        manifest: 'cache/images.json',
        formats: ['webp'],
        copyOriginals: false,
        quality: { webp: 80, avif: 50 },
        effort: { webp: 4, avif: 4 },
      },
    },
    root,
  );

  assert.deepEqual(await runImagePipeline(config), {
    sourceCount: 0,
    rasterCount: 0,
    writtenFiles: 0,
    unchangedFiles: 0,
    prunedFiles: 0,
  });
});

test('image pipeline rejects generated/original output collisions', async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'frontend-kit-images-collision-'));
  context.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, 'source'));
  const png = await sharp({
    create: { width: 1, height: 1, channels: 3, background: { r: 0, g: 0, b: 0 } },
  })
    .png()
    .toBuffer();
  const webp = await sharp(png).webp().toBuffer();
  const { writeAtomicIfChanged } = await import('./lib/files.mjs');
  await writeAtomicIfChanged(path.join(root, 'source/sample.png'), png);
  await writeAtomicIfChanged(path.join(root, 'source/sample.webp'), webp);
  const config = normalizeImageConfig(
    {
      images: {
        sourceDir: 'source',
        outputDir: 'output',
        manifest: 'cache/images.json',
        formats: ['webp'],
        copyOriginals: true,
        quality: { webp: 80, avif: 50 },
        effort: { webp: 4, avif: 4 },
      },
    },
    root,
  );

  await assert.rejects(runImagePipeline(config), /Конфликт выходных изображений/);
});
