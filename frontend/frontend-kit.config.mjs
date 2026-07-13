export default {
  fonts: {
    sourceDir: 'src/assets/fonts/source',
    outputDir: 'public/fonts',
    stylesheet: 'src/styles/generated/_fonts.scss',
    manifest: '.cache/assets/fonts.json',
    publicPath: '/fonts',
    formats: ['woff2', 'woff'],
    fontDisplay: 'swap',
    faces: [],
    inferFromFilenames: true,
  },
  images: {
    sourceDir: 'src/assets/images/source',
    outputDir: 'public/images',
    manifest: '.cache/assets/images.json',
    formats: ['webp', 'avif'],
    copyOriginals: true,
    quality: {
      webp: 80,
      avif: 50,
    },
    effort: {
      webp: 4,
      avif: 4,
    },
  },
  tokenCheck: {
    includeDirs: ['src/styles'],
    allowedDirs: ['src/styles/foundation/tokens', 'src/styles/themes'],
  },
};
