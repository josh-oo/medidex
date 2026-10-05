import { useEffect, useState } from "react";

/** Tracks the rendered height of an element (null while unmeasured or when `enabled` is false). */
export function useElementHeight(element: HTMLElement | null, enabled = true): number | null {
  const [height, setHeight] = useState<number | null>(null);

  useEffect(() => {
    if (!element || !enabled) {
      setHeight(null);
      return;
    }

    const observer = new ResizeObserver(() => {
      const measured = element.getBoundingClientRect().height;
      setHeight(measured > 0 ? measured : null);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element, enabled]);

  return height;
}
