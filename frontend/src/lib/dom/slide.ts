const activeAnimations = new WeakMap<HTMLElement, Animation>();

function getWindow(element: HTMLElement): Window | null {
  return element.ownerDocument.defaultView;
}

function finish(element: HTMLElement, hidden: boolean): void {
  element.hidden = hidden;
  element.style.removeProperty('height');
  element.style.removeProperty('overflow');
  activeAnimations.delete(element);
}

function prefersReducedMotion(view: Window): boolean {
  return view.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
}

function animateHeight(
  element: HTMLElement,
  from: number,
  to: number,
  duration: number,
  hiddenWhenFinished: boolean,
): void {
  const view = getWindow(element);
  if (!view) return;

  if (duration <= 0 || prefersReducedMotion(view)) {
    finish(element, hiddenWhenFinished);
    return;
  }

  element.style.height = `${from}px`;
  element.style.overflow = 'hidden';

  const animation = element.animate(
    [{ height: `${from}px` }, { height: `${to}px` }],
    {
      duration,
      easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
    },
  );

  activeAnimations.set(element, animation);
  animation.addEventListener('finish', () => finish(element, hiddenWhenFinished), {
    once: true,
  });
}

export function slideUp(element: HTMLElement | null, duration = 300): void {
  if (!element || activeAnimations.has(element)) return;

  const view = getWindow(element);
  if (!view) return;

  animateHeight(element, element.offsetHeight, 0, duration, true);
}

export function slideDown(element: HTMLElement | null, duration = 300): void {
  if (!element || activeAnimations.has(element)) return;

  const view = getWindow(element);
  if (!view) return;

  element.hidden = false;
  animateHeight(element, 0, element.scrollHeight, duration, false);
}

export function slideToggle(element: HTMLElement | null, duration = 300): void {
  if (!element) return;
  if (element.hidden || element.offsetHeight === 0) slideDown(element, duration);
  else slideUp(element, duration);
}

export const isSliding = (element: HTMLElement | null): boolean =>
  element ? activeAnimations.has(element) : false;
