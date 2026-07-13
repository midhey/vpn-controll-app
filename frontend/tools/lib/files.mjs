import { createHash, randomUUID } from 'node:crypto';
import { access, mkdir, readFile, rename, rmdir, stat, unlink, writeFile } from 'node:fs/promises';
import path from 'node:path';

export function sha256(content) {
  return createHash('sha256').update(content).digest('hex');
}

export async function writeAtomicIfChanged(targetPath, content) {
  const buffer = Buffer.isBuffer(content) ? content : Buffer.from(content);
  await mkdir(path.dirname(targetPath), { recursive: true });

  try {
    const existing = await readFile(targetPath);
    if (existing.length === buffer.length && sha256(existing) === sha256(buffer)) {
      return false;
    }
  } catch (error) {
    if (error?.code !== 'ENOENT') throw error;
  }

  const temporaryPath = path.join(
    path.dirname(targetPath),
    `.tmp-${path.basename(targetPath)}-${randomUUID()}`,
  );

  try {
    await writeFile(temporaryPath, buffer);
    await rename(temporaryPath, targetPath);
  } catch (error) {
    await unlink(temporaryPath).catch(() => undefined);
    throw error;
  }

  return true;
}

export async function getMtime(pathname) {
  return (await stat(pathname, { bigint: true })).mtimeNs;
}

export function compareText(left, right) {
  if (left === right) return 0;
  return left < right ? -1 : 1;
}

export function isPathInside(parentPath, candidatePath) {
  const relative = path.relative(parentPath, candidatePath);
  return relative !== '' && !relative.startsWith(`..${path.sep}`) && relative !== '..';
}

function assertManagedRelativePath(relativePath, manifestPath) {
  if (
    typeof relativePath !== 'string' ||
    !relativePath ||
    path.isAbsolute(relativePath) ||
    relativePath.includes('\\') ||
    relativePath.split('/').some((part) => part === '' || part === '.' || part === '..')
  ) {
    throw new Error(`Некорректный управляемый путь в manifest ${manifestPath}: ${relativePath}`);
  }
}

export async function readAssetManifest(manifestPath) {
  let raw;
  try {
    raw = JSON.parse(await readFile(manifestPath, 'utf8'));
  } catch (error) {
    if (error?.code === 'ENOENT') return new Map();
    if (error instanceof SyntaxError) {
      throw new Error(`Некорректный JSON asset manifest: ${manifestPath}`);
    }
    throw error;
  }

  if (raw?.version !== 1 || !raw.files || typeof raw.files !== 'object' || Array.isArray(raw.files)) {
    throw new Error(`Неподдерживаемый asset manifest: ${manifestPath}`);
  }

  const files = new Map();
  for (const [relativePath, fingerprint] of Object.entries(raw.files)) {
    assertManagedRelativePath(relativePath, manifestPath);
    if (typeof fingerprint !== 'string' || !fingerprint) {
      throw new Error(`Некорректный fingerprint в asset manifest: ${relativePath}`);
    }
    files.set(relativePath, fingerprint);
  }
  return files;
}

export async function writeAssetManifest(manifestPath, files) {
  const sortedFiles = Object.fromEntries(
    [...files.entries()].sort(([left], [right]) => compareText(left, right)),
  );
  return writeAtomicIfChanged(
    manifestPath,
    `${JSON.stringify({ version: 1, files: sortedFiles }, null, 2)}\n`,
  );
}

export async function managedFileExists(outputDir, relativePath) {
  try {
    await access(path.join(outputDir, ...relativePath.split('/')));
    return true;
  } catch (error) {
    if (error?.code === 'ENOENT') return false;
    throw error;
  }
}

async function removeEmptyParents(filePath, outputDir) {
  let directory = path.dirname(filePath);
  while (directory !== outputDir && isPathInside(outputDir, directory)) {
    try {
      await rmdir(directory);
    } catch (error) {
      if (error?.code === 'ENOENT') return;
      if (error?.code === 'ENOTEMPTY') return;
      throw error;
    }
    directory = path.dirname(directory);
  }
}

export async function pruneManagedFiles(outputDir, previousFiles, nextFiles) {
  let prunedFiles = 0;
  for (const relativePath of previousFiles.keys()) {
    if (nextFiles.has(relativePath)) continue;
    assertManagedRelativePath(relativePath, 'asset manifest');
    const filePath = path.join(outputDir, ...relativePath.split('/'));
    try {
      await unlink(filePath);
      prunedFiles += 1;
      await removeEmptyParents(filePath, outputDir);
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error;
    }
  }
  return prunedFiles;
}
