# Frontend Kit rules

- Inspect existing tokens before adding a token. Prefer semantic role names to appearance names.
- Keep raw color literals inside `src/styles/foundation/tokens/` or `src/styles/themes/`.
- Consume the public foundation Sass API; do not deep-import foundation internals.
- Preserve visible `:focus-visible`, disabled, and reduced-motion states.
- Keep `src/styles/foundation/` and `src/lib/` framework-agnostic.
- Keep product-specific styles, copy, assets, and components out of the foundation.
- Do not edit generated files by hand.
- Put source fonts in `src/assets/fonts/source/` and configure faces in `frontend-kit.config.mjs`.
- Put source images in `src/assets/images/source/`; never rewrite HTML from an asset script.
- Keep React/Vue components and adapters inside their preset workspace.
- Keep WordPress integration optional and outside foundation; consume production assets through its Vite manifest.
- Run `npm run check` and `npm run build` after material changes.
