import { readFile, readdir } from 'node:fs/promises';
import path from 'node:path';

import scss from 'postcss-scss';

import { compareText, isPathInside } from './files.mjs';

const COLOR_PATTERN = /#[\da-f]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\s*\(/giu;

async function discoverScssFiles(directory, prefix = '') {
  let entries;
  try {
    entries = await readdir(path.join(directory, prefix), { withFileTypes: true });
  } catch (error) {
    if (error?.code === 'ENOENT' && prefix === '') {
      throw new Error(`Каталог стилей не найден: ${directory}`);
    }
    throw error;
  }

  entries.sort((left, right) => compareText(left.name, right.name));
  const files = [];
  for (const entry of entries) {
    const relativePath = path.join(prefix, entry.name);
    if (entry.isDirectory()) files.push(...(await discoverScssFiles(directory, relativePath)));
    else if (entry.isFile() && path.extname(entry.name).toLowerCase() === '.scss') {
      files.push(path.join(directory, relativePath));
    }
  }
  return files;
}

export function normalizeTokenConfig(rawConfig, rootDir) {
  const raw = rawConfig?.tokenCheck;
  if (!raw || typeof raw !== 'object') {
    throw new Error('В конфигурации отсутствует объект tokenCheck.');
  }
  if (!Array.isArray(raw.includeDirs) || raw.includeDirs.length === 0) {
    throw new Error('tokenCheck.includeDirs должен содержать хотя бы один каталог.');
  }
  if (!Array.isArray(raw.allowedDirs)) {
    throw new Error('tokenCheck.allowedDirs должен быть массивом.');
  }

  const includeDirs = raw.includeDirs.map((directory, index) => {
    if (typeof directory !== 'string' || !directory.trim()) {
      throw new Error(`tokenCheck.includeDirs[${index}] должен быть непустой строкой.`);
    }
    return path.resolve(rootDir, directory);
  });
  const allowedDirs = raw.allowedDirs.map((directory, index) => {
    if (typeof directory !== 'string' || !directory.trim()) {
      throw new Error(`tokenCheck.allowedDirs[${index}] должен быть непустой строкой.`);
    }
    const resolved = path.resolve(rootDir, directory);
    if (
      !includeDirs.some(
        (includeDir) => resolved === includeDir || isPathInside(includeDir, resolved),
      )
    ) {
      throw new Error(`Разрешённый каталог находится вне includeDirs: ${directory}`);
    }
    return resolved;
  });

  return { includeDirs, allowedDirs };
}

function isAllowed(filePath, allowedDirs) {
  return allowedDirs.some(
    (directory) => filePath === directory || isPathInside(directory, filePath),
  );
}

function collectMatches(value, node, filePath) {
  const violations = [];
  for (const match of value.matchAll(COLOR_PATTERN)) {
    violations.push({
      file: filePath,
      line: node.source?.start?.line ?? 1,
      column: node.source?.start?.column ?? 1,
      value: match[0],
    });
  }
  return violations;
}

export async function findTokenViolations(config) {
  const files = (
    await Promise.all(config.includeDirs.map((directory) => discoverScssFiles(directory)))
  )
    .flat()
    .sort(compareText);
  const violations = [];

  for (const filePath of files) {
    if (isAllowed(filePath, config.allowedDirs)) continue;
    const source = await readFile(filePath, 'utf8');
    const root = scss.parse(source, { from: filePath });
    root.walkDecls((declaration) => {
      violations.push(...collectMatches(declaration.value, declaration, filePath));
    });
    root.walkAtRules((atRule) => {
      violations.push(...collectMatches(atRule.params, atRule, filePath));
    });
  }

  return violations;
}
