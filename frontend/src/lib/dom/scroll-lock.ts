interface ScrollLockState {
  scrollY: number;
  bodyStyles: Partial<Record<'position' | 'top' | 'left' | 'right' | 'width', string>>;
}

let state: ScrollLockState | undefined;

const canUseDOM = (): boolean =>
  typeof window !== 'undefined' && typeof document !== 'undefined';

export function lockScroll(): void {
  if (!canUseDOM() || state) return;

  const { body, documentElement } = document;
  const scrollY = window.scrollY || documentElement.scrollTop || 0;

  state = {
    scrollY,
    bodyStyles: {
      position: body.style.position,
      top: body.style.top,
      left: body.style.left,
      right: body.style.right,
      width: body.style.width,
    },
  };

  Object.assign(body.style, {
    position: 'fixed',
    top: `-${scrollY}px`,
    left: '0',
    right: '0',
    width: '100%',
  });
  documentElement.classList.add('is-scroll-locked');
}

export function unlockScroll(): void {
  if (!canUseDOM() || !state) return;

  const { body, documentElement } = document;
  const { scrollY, bodyStyles } = state;
  state = undefined;

  Object.assign(body.style, bodyStyles);
  documentElement.classList.remove('is-scroll-locked');

  const previousBehavior = documentElement.style.scrollBehavior;
  documentElement.style.scrollBehavior = 'auto';
  window.scrollTo({ top: scrollY, left: 0, behavior: 'auto' });
  documentElement.style.scrollBehavior = previousBehavior;
}

export const isScrollLocked = (): boolean => state !== undefined;
