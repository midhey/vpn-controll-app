import { mkdir, readFile, readdir } from 'node:fs/promises';
import path from 'node:path';

import sharp from 'sharp';

import {
  compareText,
  isPathInside,
  managedFileExists,
  pruneManagedFiles,
  readAssetManifest,
  sha256,
  writeAssetManifest,
  writeAtomicIfChanged,
} from './files.mjs';

const IMAGE_PIPELINE_VERSION = 1;

const COPY_EXTENSIONS = new Set([
  '.avif',
  '.gif',
  '.ico',
  '.jpeg',
  '.jpg',
  '.png',
  '.svg',
  '.webp',
]);
const RASTER_EXTENSIONS = new Set(['.jpeg', '.jpg', '.png']);
const OUTPUT_FORMATS = new Set(['webp', 'avif']);
const FORMAT_ORDER = new Map([
  ['webp', 0],
  ['avif', 1],
]);

function validateInteger(value, label, min, max) {
  if (!Number.isInteger(value) || value < min || value > max) {
    throw new Error(`${label} должен быть целым числом от ${min} до ${max}.`);
  }
  return value;
}

export function normalizeImageConfig(rawConfig, rootDir) {
  const raw = rawConfig?.images;
  if (!raw || typeof raw !== 'object') {
    throw new Error('В конфигурации отсутствует объект images.');
  }

  for (const key of ['sourceDir', 'outputDir']) {
    if (typeof raw[key] !== 'string' || !raw[key].trim()) {
      throw new Error(`images.${key} должен быть непустой строкой.`);
    }
  }
  if (typeof raw.manifest !== 'string' || !raw.manifest.trim()) {
    throw new Error('images.manifest должен быть непустой строкой.');
  }

  if (!Array.isArray(raw.formats)) {
    throw new Error('images.formats должен быть массивом.');
  }

  const formats = [...new Set(raw.formats)];
  for (const format of formats) {
    if (!OUTPUT_FORMATS.has(format)) {
      throw new Error(`Неподдерживаемый формат изображения: ${format}`);
    }
  }
  formats.sort((left, right) => FORMAT_ORDER.get(left) - FORMAT_ORDER.get(right));

  if (raw.copyOriginals !== true && raw.copyOriginals !== false) {
    throw new Error('images.copyOriginals должен быть boolean.');
  }
  if (!raw.copyOriginals && formats.length === 0) {
    throw new Error('Включите copyOriginals или укажите хотя бы один выходной формат.');
  }

  const sourceDir = path.resolve(rootDir, raw.sourceDir);
  const outputDir = path.resolve(rootDir, raw.outputDir);
  if (sourceDir === outputDir || isPathInside(sourceDir, outputDir)) {
    throw new Error('images.outputDir не может находиться внутри images.sourceDir.');
  }

  return {
    sourceDir,
    outputDir,
    manifest: path.resolve(rootDir, raw.manifest),
    formats,
    copyOriginals: raw.copyOriginals,
    quality: {
      webp: validateInteger(raw.quality?.webp, 'images.quality.webp', 1, 100),
      avif: validateInteger(raw.quality?.avif, 'images.quality.avif', 1, 100),
    },
    effort: {
      webp: validateInteger(raw.effort?.webp, 'images.effort.webp', 0, 6),
      avif: validateInteger(raw.effort?.avif, 'images.effort.avif', 0, 9),
    },
  };
}

async function discoverFiles(directory, prefix = '') {
  let entries;
  try {
    entries = await readdir(path.join(directory, prefix), { withFileTypes: true });
  } catch (error) {
    if (error?.code === 'ENOENT' && prefix === '') {
      throw new Error(`Каталог исходных изображений не найден: ${directory}`);
    }
    throw error;
  }

  entries.sort((left, right) => compareText(left.name, right.name));
  const files = [];
  for (const entry of entries) {
    const relativePath = path.join(prefix, entry.name);
    if (entry.isDirectory()) files.push(...(await discoverFiles(directory, relativePath)));
    else if (entry.isFile() && COPY_EXTENSIONS.has(path.extname(entry.name).toLowerCase())) {
      files.push(relativePath);
    }
  }
  return files;
}

function convertedRelativePath(relativePath, format) {
  const extension = path.extname(relativePath);
  return `${relativePath.slice(0, -extension.length)}.${format}`;
}

function toManifestPath(relativePath) {
  return relativePath.split(path.sep).join('/');
}

function imageFingerprint(sourceDigest, format, config) {
  const encoderVersion = sharp.versions.sharp ?? 'unknown';
  const libvipsVersion = sharp.versions.vips ?? 'unknown';
  return sha256(
    [
      `pipeline:${IMAGE_PIPELINE_VERSION}`,
      `sharp:${encoderVersion}`,
      `libvips:${libvipsVersion}`,
      `source:${sourceDigest}`,
      `format:${format}`,
      `quality:${config.quality[format]}`,
      `effort:${config.effort[format]}`,
      'autoOrient:true',
    ].join('\n'),
  );
}

function assertNoOutputCollisions(files, config) {
  const outputs = new Set();
  const register = (relativePath) => {
    const normalized = relativePath.toLowerCase();
    if (outputs.has(normalized)) {
      throw new Error(`Конфликт выходных изображений: ${relativePath}`);
    }
    outputs.add(normalized);
  };

  for (const relativePath of files) {
    if (config.copyOriginals) register(relativePath);
    if (!RASTER_EXTENSIONS.has(path.extname(relativePath).toLowerCase())) continue;
    for (const format of config.formats) register(convertedRelativePath(relativePath, format));
  }
}

export function assertImageMagic(buffer, format, label = 'image buffer') {
  const value = Buffer.from(buffer);
  const isWebp =
    format === 'webp' &&
    value.length >= 12 &&
    value.subarray(0, 4).toString('ascii') === 'RIFF' &&
    value.subarray(8, 12).toString('ascii') === 'WEBP';
  const header = value.subarray(0, 32).toString('ascii');
  const isAvif =
    format === 'avif' &&
    value.length >= 16 &&
    value.subarray(4, 8).toString('ascii') === 'ftyp' &&
    /avif|avis/.test(header);

  if (!isWebp && !isAvif) {
    throw new Error(`Некорректная сигнатура ${format} в ${label}`);
  }
}

async function convertImage(sourceBuffer, format, config) {
  const pipeline = sharp(sourceBuffer, { failOn: 'warning' }).autoOrient();
  if (format === 'webp') {
    return pipeline.webp({ quality: config.quality.webp, effort: config.effort.webp }).toBuffer();
  }
  return pipeline.avif({ quality: config.quality.avif, effort: config.effort.avif }).toBuffer();
}

export async function runImagePipeline(config, options = {}) {
  const converter = options.converter ?? convertImage;
  const logger = options.logger ?? { info: () => undefined };
  const files = await discoverFiles(config.sourceDir);
  const rasterFiles = files.filter((file) =>
    RASTER_EXTENSIONS.has(path.extname(file).toLowerCase()),
  );
  assertNoOutputCollisions(files, config);
  await mkdir(config.outputDir, { recursive: true });
  const previousFiles = await readAssetManifest(config.manifest);
  const nextFiles = new Map();

  let writtenFiles = 0;
  let unchangedFiles = 0;

  for (const relativePath of files) {
    const sourcePath = path.join(config.sourceDir, relativePath);
    const sourceBuffer = await readFile(sourcePath);
    const sourceDigest = sha256(sourceBuffer);

    if (config.copyOriginals) {
      const manifestPath = toManifestPath(relativePath);
      const fingerprint = sha256(`copy:v1\nsource:${sourceDigest}`);
      nextFiles.set(manifestPath, fingerprint);
      if (
        previousFiles.get(manifestPath) === fingerprint &&
        (await managedFileExists(config.outputDir, manifestPath))
      ) {
        unchangedFiles += 1;
      } else {
        const changed = await writeAtomicIfChanged(
          path.join(config.outputDir, relativePath),
          sourceBuffer,
        );
        if (changed) writtenFiles += 1;
        else unchangedFiles += 1;
      }
    }

    if (!RASTER_EXTENSIONS.has(path.extname(relativePath).toLowerCase())) continue;
    for (const format of config.formats) {
      const outputRelativePath = convertedRelativePath(relativePath, format);
      const manifestPath = toManifestPath(outputRelativePath);
      const fingerprint = imageFingerprint(sourceDigest, format, config);
      nextFiles.set(manifestPath, fingerprint);
      if (
        previousFiles.get(manifestPath) === fingerprint &&
        (await managedFileExists(config.outputDir, manifestPath))
      ) {
        unchangedFiles += 1;
        continue;
      }

      const outputBuffer = await converter(sourceBuffer, format, config);
      assertImageMagic(outputBuffer, format, `${relativePath} → ${format}`);
      const outputPath = path.join(config.outputDir, outputRelativePath);
      const changed = await writeAtomicIfChanged(outputPath, outputBuffer);
      if (changed) writtenFiles += 1;
      else unchangedFiles += 1;
    }
  }

  const prunedFiles = await pruneManagedFiles(config.outputDir, previousFiles, nextFiles);
  await writeAssetManifest(config.manifest, nextFiles);

  if (files.length === 0) {
    logger.info(`Каталог исходных изображений пуст: ${config.sourceDir}`);
  }

  return {
    sourceCount: files.length,
    rasterCount: rasterFiles.length,
    writtenFiles,
    unchangedFiles,
    prunedFiles,
  };
}
