#!/usr/bin/env node
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { findTokenViolations, normalizeTokenConfig } from './lib/tokens.mjs';

function readConfigArgument(argv) {
  const index = argv.indexOf('--config');
  if (index === -1) return 'frontend-kit.config.mjs';
  if (!argv[index + 1]) throw new Error('После --config необходимо указать путь к файлу.');
  return argv[index + 1];
}

async function main() {
  const configArgument = readConfigArgument(process.argv.slice(2));
  const configPath = path.resolve(process.cwd(), configArgument);
  const configModule = await import(pathToFileURL(configPath).href);
  const config = normalizeTokenConfig(configModule.default, path.dirname(configPath));
  const violations = await findTokenViolations(config);

  if (violations.length === 0) {
    console.log('Проверка токенов пройдена: прямых цветовых литералов нет.');
    return;
  }

  for (const violation of violations) {
    console.error(
      `${path.relative(process.cwd(), violation.file)}:${violation.line}:${violation.column} — прямой цвет ${violation.value}`,
    );
  }
  throw new Error(`Найдено нарушений: ${violations.length}.`);
}

main().catch((error) => {
  console.error(`Ошибка проверки токенов: ${error.message}`);
  process.exitCode = 1;
});
