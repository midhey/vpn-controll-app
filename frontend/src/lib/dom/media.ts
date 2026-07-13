const canUseMatchMedia = (): boolean =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function';

export const isCoarsePointer = (): boolean =>
  canUseMatchMedia() && window.matchMedia('(pointer: coarse)').matches;

export const isHoverUnavailable = (): boolean =>
  canUseMatchMedia() && window.matchMedia('(hover: none)').matches;
