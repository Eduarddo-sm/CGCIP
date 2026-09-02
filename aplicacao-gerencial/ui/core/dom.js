export const $ = (selector) => document.querySelector(selector);

export function preserveScroll(target, render) {
  const element = typeof target === "string" ? $(target) : target;
  if (!element) return render();

  const scrollTop = element.scrollTop;
  const scrollLeft = element.scrollLeft;
  const restore = () => {
    element.scrollTop = Math.min(scrollTop, Math.max(0, element.scrollHeight - element.clientHeight));
    element.scrollLeft = Math.min(scrollLeft, Math.max(0, element.scrollWidth - element.clientWidth));
  };

  const result = render();
  restore();
  requestAnimationFrame(restore);
  return result;
}

export function captureScrollState(targets = []) {
  const viewport = {
    x: window.scrollX,
    y: window.scrollY,
  };
  const elements = targets
    .map((target) => ({
      selector: typeof target === "string" ? target : null,
      element: typeof target === "string" ? $(target) : target,
    }))
    .filter(({ element }) => Boolean(element))
    .map(({ selector, element }) => ({
      selector,
      element,
      left: element.scrollLeft,
      top: element.scrollTop,
    }));

  const restore = () => {
    window.scrollTo(viewport.x, viewport.y);
    elements.forEach(({ selector, element, left, top }) => {
      const current = selector ? $(selector) : element;
      if (!current) return;
      current.scrollTop = Math.min(top, Math.max(0, current.scrollHeight - current.clientHeight));
      current.scrollLeft = Math.min(left, Math.max(0, current.scrollWidth - current.clientWidth));
    });
  };

  return () => {
    restore();
    queueMicrotask(restore);
    requestAnimationFrame(() => {
      restore();
      requestAnimationFrame(restore);
    });
    window.setTimeout(restore, 60);
    window.setTimeout(restore, 180);
  };
}
