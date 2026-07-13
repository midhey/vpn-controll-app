export interface PluralForms {
  one: string;
  few: string;
  many: string;
  other?: string;
}

export function pluralize(
  count: number,
  forms: PluralForms,
  locale = 'ru-RU',
): string {
  const category = new Intl.PluralRules(locale).select(count);

  if (category === 'one') return forms.one;
  if (category === 'few') return forms.few;
  if (category === 'many') return forms.many;
  return forms.other ?? forms.many;
}
