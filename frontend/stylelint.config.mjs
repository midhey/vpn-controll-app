/** @type {import('stylelint').Config} */
export default {
  extends: ['stylelint-config-standard-scss'],
  rules: {
    'selector-class-pattern': [
      '^[a-z][a-z0-9]*(?:-[a-z0-9]+)*(?:__(?:[a-z0-9]+(?:-[a-z0-9]+)*))?(?:--(?:[a-z0-9]+(?:-[a-z0-9]+)*))?$',
      { message: 'Use kebab-case or BEM class names.' },
    ],
    'scss/at-use-no-unnamespaced': true,
    'scss/load-no-partial-leading-underscore': true,
    'scss/no-global-function-names': true,
  },
};
