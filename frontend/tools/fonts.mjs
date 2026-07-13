#!/usr/bin/env node
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { normalizeFontConfig, runFontPipeline } from './lib/fonts.mjs';

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
  const config = normalizeFontConfig(configModule.default, path.dirname(configPath));
  const result = await runFontPipeline(config, {
    logger: {
      info: (message) => console.log(message),
      warn: (message) => console.warn(`Предупреждение: ${message}`),
    },
  });

  if (result.sourceCount === 0) {
    console.log('Шрифты не найдены — обработка успешно завершена без конвертации.');
    return;
  }

  console.log(
    `Шрифты готовы: faces — ${result.faceCount}, записано — ${result.writtenFiles}, без изменений — ${result.unchangedFiles}, удалено устаревших — ${result.prunedFiles}.`,
  );
}

main().catch((error) => {
  console.error(`Ошибка обработки шрифтов: ${error.message}`);
  process.exitCode = 1;
});
