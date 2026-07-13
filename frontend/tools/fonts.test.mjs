import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  getMtime,
  inferFaceMetadata,
  normalizeFontConfig,
  renderFontStylesheet,
  runFontPipeline,
  writeAtomicIfChanged,
} from './lib/fonts.mjs';

test('font config accepts safe relative public paths for backend builds', () => {
  const rawConfig = {
    fonts: {
      sourceDir: 'source',
      outputDir: 'output',
      stylesheet: 'generated/_fonts.scss',
      manifest: 'cache/fonts.json',
      publicPath: '../fonts/',
      formats: ['woff2'],
      fontDisplay: 'swap',
      faces: [],
      inferFromFilenames: true,
    },
  };

  assert.equal(normalizeFontConfig(rawConfig, '/tmp/project').publicPath, '../fonts');
  assert.throws(
    () =>
      normalizeFontConfig(
        { ...rawConfig, fonts: { ...rawConfig.fonts, publicPath: 'https://example.com/fonts' } },
        '/tmp/project',
      ),
    /локальным URL-префиксом/,
  );
});

test('font pipeline prunes outputs removed from the source set', async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'frontend-kit-font-pruning-'));
  context.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(path.join(root, 'source'));
  await writeAtomicIfChanged(
    path.join(root, 'source/Example-Regular.ttf'),
    Buffer.from([0x00, 0x01, 0x00, 0x00, 0x01]),
  );
  const config = normalizeFontConfig(
    {
      fonts: {
        sourceDir: 'source',
        outputDir: 'output',
        stylesheet: 'generated/_fonts.scss',
        manifest: 'cache/fonts.json',
        publicPath: '/fonts',
        formats: ['woff2', 'woff'],
        fontDisplay: 'swap',
        faces: [],
        inferFromFilenames: true,
      },
    },
    root,
  );

  const first = await runFontPipeline(config, {
    converters: {
      woff: () => Buffer.from('wOFF-output'),
      woff2: () => Buffer.from('wOF2-output'),
    },
  });
  assert.equal(first.prunedFiles, 0);
  await readFile(path.join(root, 'output/Example-Regular.woff'));
  await readFile(path.join(root, 'output/Example-Regular.woff2'));

  await rm(path.join(root, 'source/Example-Regular.ttf'));
  const second = await runFontPipeline(config);
  assert.equal(second.prunedFiles, 2);
  await assert.rejects(readFile(path.join(root, 'output/Example-Regular.woff')), {
    code: 'ENOENT',
  });
  assert.equal(await readFile(path.join(root, 'generated/_fonts.scss'), 'utf8'), '// Generated file. Do not edit.\n');
});

test('filename inference recognises family, weight and style markers', () => {
  assert.deepEqual(inferFaceMetadata('OpenSans-BoldItalic.ttf'), {
    file: 'OpenSans-BoldItalic.ttf',
    family: 'Open Sans',
    weight: 700,
    style: 'italic',
    basename: 'OpenSans-BoldItalic',
  });
  assert.equal(inferFaceMetadata('Unbounded-SemiBold.otf').weight, 600);
  assert.equal(inferFaceMetadata('Source_Sans_3-ExtraBoldOblique.ttf').style, 'oblique');
  assert.equal(inferFaceMetadata('Source_Sans_3-ExtraBoldOblique.ttf').weight, 800);
  assert.equal(inferFaceMetadata('Brand-Regular.ttf').weight, 400);
});

test('stylesheet output is deterministic and formats have a stable order', () => {
  const regular = {
    file: 'Example-Regular.ttf',
    family: 'Example',
    weight: 400,
    style: 'normal',
    outputs: [
      { format: 'woff', url: '/fonts/Example-Regular.woff' },
      { format: 'woff2', url: '/fonts/Example-Regular.woff2' },
    ],
  };
  const bold = {
    file: 'Example-Bold.ttf',
    family: 'Example',
    weight: 700,
    style: 'normal',
    outputs: [{ format: 'woff2', url: '/fonts/Example-Bold.woff2' }],
  };

  const first = renderFontStylesheet([bold, regular], 'swap');
  const second = renderFontStylesheet([regular, bold], 'swap');

  assert.equal(first, second);
  assert.match(first, /^\/\/ Generated file\. Do not edit\./);
  assert.ok(
    first.indexOf('Example-Regular.woff2") format') <
      first.indexOf('Example-Regular.woff") format'),
  );
  assert.ok(first.indexOf('font-weight: 400') < first.indexOf('font-weight: 700'));
  assert.match(first, /font-family: Example;/);

  const spacedFamily = renderFontStylesheet(
    [{ ...regular, family: 'Open Sans' }],
    'swap',
  );
  assert.match(spacedFamily, /font-family: "Open Sans";/);
});

test('atomic writer preserves an unchanged file and replaces changed content', async (context) => {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'frontend-kit-fonts-'));
  context.after(() => rm(directory, { recursive: true, force: true }));
  const target = path.join(directory, 'nested', 'font.woff2');

  assert.equal(await writeAtomicIfChanged(target, Buffer.from('first')), true);
  const initialMtime = await getMtime(target);
  assert.equal(await writeAtomicIfChanged(target, Buffer.from('first')), false);
  assert.equal(await getMtime(target), initialMtime);

  assert.equal(await writeAtomicIfChanged(target, Buffer.from('second')), true);
  assert.equal((await readFile(target, 'utf8')), 'second');
});
