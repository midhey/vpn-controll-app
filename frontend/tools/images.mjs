#!/usr/bin/env node
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { normalizeImageConfig, runImagePipeline } from './lib/images.mjs';

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
  const config = normalizeImageConfig(configModule.default, path.dirname(configPath));
  const result = await runImagePipeline(config, {
    logger: { info: (message) => console.log(message) },
  });

  if (result.sourceCount === 0) {
    console.log('Изображения не найдены — обработка успешно завершена.');
    return;
  }

  console.log(
    `Изображения готовы: исходников — ${result.sourceCount}, raster — ${result.rasterCount}, записано — ${result.writtenFiles}, без изменений — ${result.unchangedFiles}, удалено устаревших — ${result.prunedFiles}.`,
  );
}

main().catch((error) => {
  console.error(`Ошибка обработки изображений: ${error.message}`);
  process.exitCode = 1;
});
