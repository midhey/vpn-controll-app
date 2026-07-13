import { readFile, readdir, mkdir } from 'node:fs/promises';
import path from 'node:path';

import { createFont } from 'fonteditor-core';
import ttf2woff from 'ttf2woff';
import ttf2woff2 from 'ttf2woff2';

import {
  compareText,
  pruneManagedFiles,
  readAssetManifest,
  sha256,
  writeAssetManifest,
  writeAtomicIfChanged,
} from './files.mjs';

export { getMtime, writeAtomicIfChanged } from './files.mjs';

const SOURCE_FORMATS = new Set(['.ttf', '.otf']);
const OUTPUT_FORMATS = new Set(['woff2', 'woff']);
const FONT_DISPLAY_VALUES = new Set(['auto', 'block', 'swap', 'fallback', 'optional']);
const STYLE_VALUES = new Set(['normal', 'italic', 'oblique']);
const RESERVED_FONT_FAMILIES = new Set([
  'cursive',
  'emoji',
  'fangsong',
  'fantasy',
  'inherit',
  'initial',
  'math',
  'monospace',
  'revert',
  'revert-layer',
  'sans-serif',
  'serif',
  'system-ui',
  'ui-monospace',
  'ui-rounded',
  'ui-sans-serif',
  'ui-serif',
  'unset',
]);
const FORMAT_ORDER = new Map([
  ['woff2', 0],
  ['woff', 1],
]);

const WEIGHTS = new Map([
  ['thin', 100],
  ['extralight', 200],
  ['light', 300],
  ['regular', 400],
  ['medium', 500],
  ['semibold', 600],
  ['bold', 700],
  ['extrabold', 800],
  ['black', 900],
]);

const STYLE_MARKERS = new Map([
  ['italic', 'italic'],
  ['oblique', 'oblique'],
]);

function splitFilename(filename) {
  const extension = path.extname(filename);
  const basename = path.basename(filename, extension);
  const words = basename
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z\d])([A-Z])/g, '$1 $2')
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  return { basename, extension: extension.toLowerCase(), words };
}

function takeMarker(words, markers) {
  for (const size of [2, 1]) {
    if (words.length < size) continue;
    const marker = words.slice(-size).join('').toLowerCase();
    if (!markers.has(marker)) continue;
    words.splice(-size, size);
    return markers.get(marker);
  }

  return undefined;
}

export function inferFaceMetadata(filename) {
  const { basename, extension, words } = splitFilename(filename);

  if (!SOURCE_FORMATS.has(extension)) {
    throw new Error(`Неподдерживаемый исходный формат шрифта: ${filename}`);
  }

  let weight = 400;
  let style = 'normal';
  let markerFound = true;

  while (markerFound && words.length > 0) {
    markerFound = false;
    const inferredStyle = takeMarker(words, STYLE_MARKERS);
    if (inferredStyle) {
      style = inferredStyle;
      markerFound = true;
      continue;
    }

    const inferredWeight = takeMarker(words, WEIGHTS);
    if (inferredWeight) {
      weight = inferredWeight;
      markerFound = true;
    }
  }

  const family = words.join(' ').trim();
  if (!family) {
    throw new Error(`Не удалось определить семейство из имени файла: ${filename}`);
  }

  return { file: filename, family, weight, style, basename };
}

function validateFace(face, label) {
  if (!face || typeof face !== 'object') {
    throw new Error(`${label}: ожидается объект с метаданными шрифта.`);
  }

  if (typeof face.file !== 'string' || !face.file.trim()) {
    throw new Error(`${label}: поле file обязательно.`);
  }
  if (path.basename(face.file) !== face.file) {
    throw new Error(`${label}: file должен содержать только имя файла без пути.`);
  }

  const extension = path.extname(face.file).toLowerCase();
  if (!SOURCE_FORMATS.has(extension)) {
    throw new Error(`${label}: поддерживаются только файлы TTF и OTF.`);
  }

  if (typeof face.family !== 'string' || !face.family.trim()) {
    throw new Error(`${label}: поле family обязательно.`);
  }
  if (!Number.isInteger(face.weight) || face.weight < 1 || face.weight > 1000) {
    throw new Error(`${label}: weight должен быть целым числом от 1 до 1000.`);
  }
  if (!STYLE_VALUES.has(face.style)) {
    throw new Error(`${label}: style должен быть normal, italic или oblique.`);
  }

  return {
    file: face.file,
    family: face.family.trim(),
    weight: face.weight,
    style: face.style,
    basename: path.basename(face.file, extension),
  };
}

export function normalizeFontConfig(rawConfig, rootDir) {
  const raw = rawConfig?.fonts;
  if (!raw || typeof raw !== 'object') {
    throw new Error('В конфигурации отсутствует объект fonts.');
  }

  const requiredPaths = ['sourceDir', 'outputDir', 'stylesheet'];
  for (const key of requiredPaths) {
    if (typeof raw[key] !== 'string' || !raw[key].trim()) {
      throw new Error(`fonts.${key} должен быть непустой строкой.`);
    }
  }
  if (typeof raw.manifest !== 'string' || !raw.manifest.trim()) {
    throw new Error('fonts.manifest должен быть непустой строкой.');
  }

  if (
    typeof raw.publicPath !== 'string' ||
    !raw.publicPath.trim() ||
    /[\\?#]/u.test(raw.publicPath) ||
    /^[a-z][a-z\d+.-]*:/iu.test(raw.publicPath)
  ) {
    throw new Error('fonts.publicPath должен быть локальным URL-префиксом без query/hash.');
  }

  if (!Array.isArray(raw.formats) || raw.formats.length === 0) {
    throw new Error('fonts.formats должен содержать хотя бы один формат.');
  }

  const formats = [...new Set(raw.formats)];
  for (const format of formats) {
    if (!OUTPUT_FORMATS.has(format)) {
      throw new Error(`Неподдерживаемый выходной формат: ${format}`);
    }
  }
  formats.sort((left, right) => FORMAT_ORDER.get(left) - FORMAT_ORDER.get(right));

  if (!FONT_DISPLAY_VALUES.has(raw.fontDisplay)) {
    throw new Error(`Неподдерживаемое значение font-display: ${raw.fontDisplay}`);
  }

  if (!Array.isArray(raw.faces)) {
    throw new Error('fonts.faces должен быть массивом.');
  }

  return {
    sourceDir: path.resolve(rootDir, raw.sourceDir),
    outputDir: path.resolve(rootDir, raw.outputDir),
    stylesheet: path.resolve(rootDir, raw.stylesheet),
    manifest: path.resolve(rootDir, raw.manifest),
    publicPath: raw.publicPath.replace(/\/+$/, ''),
    formats,
    fontDisplay: raw.fontDisplay,
    faces: raw.faces.map((face, index) => validateFace(face, `fonts.faces[${index}]`)),
    inferFromFilenames: raw.inferFromFilenames === true,
  };
}

export function assertFontMagic(buffer, format, label = 'font buffer') {
  const value = Buffer.from(buffer);
  if (value.length < 4) throw new Error(`Файл слишком короткий: ${label}`);

  const ascii = value.subarray(0, 4).toString('ascii');
  const hex = value.subarray(0, 4).toString('hex');
  const valid =
    (format === 'ttf' && (hex === '00010000' || ascii === 'true')) ||
    (format === 'otf' && ascii === 'OTTO') ||
    (format === 'woff' && ascii === 'wOFF') ||
    (format === 'woff2' && ascii === 'wOF2');

  if (!valid) {
    throw new Error(`Некорректная сигнатура ${JSON.stringify(ascii)} в ${label}`);
  }
}

function toBuffer(value) {
  if (Buffer.isBuffer(value)) return value;
  if (ArrayBuffer.isView(value)) {
    return Buffer.from(value.buffer, value.byteOffset, value.byteLength);
  }
  if (value instanceof ArrayBuffer) return Buffer.from(value);
  throw new TypeError('Конвертер вернул неподдерживаемый тип данных.');
}

export function convertOtfToTtf(otfBuffer) {
  assertFontMagic(otfBuffer, 'otf', 'исходный OTF');
  const font = createFont(otfBuffer, { type: 'otf' });
  return toBuffer(font.write({ type: 'ttf' }));
}

export function convertTtfToWoff(ttfBuffer) {
  return toBuffer(ttf2woff(new Uint8Array(ttfBuffer), {}));
}

export function convertTtfToWoff2(ttfBuffer) {
  return toBuffer(ttf2woff2(ttfBuffer));
}

function escapeScssString(value) {
  return value.replaceAll('\\', '\\\\').replaceAll('"', '\\"');
}

function renderFontFamily(family) {
  const isIdentifier = /^-?[_a-z][-_a-z\d]*$/iu.test(family);
  if (isIdentifier && !RESERVED_FONT_FAMILIES.has(family.toLowerCase())) return family;
  return `"${escapeScssString(family)}"`;
}

function faceComparator(left, right) {
  return (
    compareText(left.family, right.family) ||
    left.weight - right.weight ||
    compareText(left.style, right.style) ||
    compareText(left.file, right.file)
  );
}

export function renderFontStylesheet(faces, fontDisplay) {
  const header = '// Generated file. Do not edit.\n';
  const sortedFaces = [...faces].sort(faceComparator);
  if (sortedFaces.length === 0) return header;

  const rules = sortedFaces.map((face) => {
    const sources = [...face.outputs]
      .sort((left, right) => FORMAT_ORDER.get(left.format) - FORMAT_ORDER.get(right.format))
      .map((output) => `url("${escapeScssString(output.url)}") format("${output.format}")`)
      .join(',\n    ');

    return `@font-face {\n  font-family: ${renderFontFamily(face.family)};\n  src:\n    ${sources};\n  font-weight: ${face.weight};\n  font-style: ${face.style};\n  font-display: ${fontDisplay};\n}`;
  });

  return `${header}\n${rules.join('\n\n')}\n`;
}

async function collectFaces(config) {
  let entries;
  try {
    entries = await readdir(config.sourceDir, { withFileTypes: true });
  } catch (error) {
    if (error?.code === 'ENOENT') {
      throw new Error(`Каталог исходных шрифтов не найден: ${config.sourceDir}`);
    }
    throw error;
  }

  const fontFiles = entries
    .filter((entry) => entry.isFile() && SOURCE_FORMATS.has(path.extname(entry.name).toLowerCase()))
    .map((entry) => entry.name)
    .sort(compareText);
  const availableFiles = new Set(fontFiles);
  const configuredFiles = new Set();
  const faces = [];

  for (const face of config.faces) {
    if (configuredFiles.has(face.file)) {
      throw new Error(`Файл указан в fonts.faces несколько раз: ${face.file}`);
    }
    if (!availableFiles.has(face.file)) {
      throw new Error(`Настроенный файл шрифта не найден: ${face.file}`);
    }
    configuredFiles.add(face.file);
    faces.push(face);
  }

  if (config.inferFromFilenames) {
    for (const file of fontFiles) {
      if (!configuredFiles.has(file)) faces.push(inferFaceMetadata(file));
    }
  }

  const outputNames = new Set();
  for (const face of faces) {
    const normalizedName = face.basename.toLowerCase();
    if (outputNames.has(normalizedName)) {
      throw new Error(`Конфликт имён выходных файлов: ${face.basename}`);
    }
    outputNames.add(normalizedName);
  }

  return { faces: faces.sort(faceComparator), sourceCount: fontFiles.length };
}

export async function runFontPipeline(config, options = {}) {
  const converters = {
    otfToTtf: options.converters?.otfToTtf ?? convertOtfToTtf,
    woff: options.converters?.woff ?? convertTtfToWoff,
    woff2: options.converters?.woff2 ?? convertTtfToWoff2,
  };
  const logger = options.logger ?? { info: () => undefined, warn: () => undefined };
  const { faces, sourceCount } = await collectFaces(config);
  const previousFiles = await readAssetManifest(config.manifest);
  const nextFiles = new Map();

  if (sourceCount === 0) {
    await mkdir(config.outputDir, { recursive: true });
    await writeAtomicIfChanged(config.stylesheet, renderFontStylesheet([], config.fontDisplay));
    const prunedFiles = await pruneManagedFiles(config.outputDir, previousFiles, nextFiles);
    await writeAssetManifest(config.manifest, nextFiles);
    logger.info(`Каталог исходных шрифтов пуст: ${config.sourceDir}`);
    return {
      sourceCount,
      faceCount: 0,
      writtenFiles: 0,
      unchangedFiles: 0,
      prunedFiles,
      warnings: [],
    };
  }

  if (faces.length === 0) {
    throw new Error('Исходные шрифты найдены, но ни один face не настроен и inference отключён.');
  }

  await mkdir(config.outputDir, { recursive: true });
  const generatedFaces = [];
  const warnings = [];
  let writtenFiles = 0;
  let unchangedFiles = 0;

  for (const face of faces) {
    const sourcePath = path.join(config.sourceDir, face.file);
    const sourceBuffer = await readFile(sourcePath);
    const sourceFormat = path.extname(face.file).slice(1).toLowerCase();
    assertFontMagic(sourceBuffer, sourceFormat, sourcePath);

    const ttfBuffer =
      sourceFormat === 'otf' ? toBuffer(await converters.otfToTtf(sourceBuffer)) : sourceBuffer;
    assertFontMagic(ttfBuffer, 'ttf', `${face.file} после преобразования в TTF`);

    const outputs = [];
    for (const format of config.formats) {
      try {
        const outputBuffer = toBuffer(await converters[format](ttfBuffer));
        assertFontMagic(outputBuffer, format, `${face.file} → ${format}`);
        const outputFilename = `${face.basename}.${format}`;
        const outputPath = path.join(config.outputDir, outputFilename);
        const changed = await writeAtomicIfChanged(outputPath, outputBuffer);
        nextFiles.set(outputFilename, sha256(outputBuffer));
        if (changed) writtenFiles += 1;
        else unchangedFiles += 1;
        outputs.push({
          format,
          url: `${config.publicPath}/${encodeURIComponent(outputFilename)}`,
        });
      } catch (error) {
        const warning = `${face.file}: не удалось создать ${format}: ${error.message}`;
        warnings.push(warning);
        logger.warn(warning);
      }
    }

    if (outputs.length === 0) {
      throw new Error(`${face.file}: не удалось создать ни одного выходного формата.`);
    }

    generatedFaces.push({ ...face, outputs });
  }

  const stylesheet = renderFontStylesheet(generatedFaces, config.fontDisplay);
  const stylesheetChanged = await writeAtomicIfChanged(config.stylesheet, stylesheet);
  if (stylesheetChanged) writtenFiles += 1;
  else unchangedFiles += 1;
  const prunedFiles = await pruneManagedFiles(config.outputDir, previousFiles, nextFiles);
  await writeAssetManifest(config.manifest, nextFiles);

  return {
    sourceCount,
    faceCount: generatedFaces.length,
    writtenFiles,
    unchangedFiles,
    prunedFiles,
    warnings,
  };
}
