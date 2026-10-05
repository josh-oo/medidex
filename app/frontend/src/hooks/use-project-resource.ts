import { useEffect, useState } from "react";
import { isNotFound } from "@/lib/api/errors";

/**
 * Loads a project-scoped resource. Resets whenever `deps` change; a 404 sets `notFound`,
 * any other failure is logged and resolved to `fallback`. While `enabled` is false nothing
 * is fetched and `data` stays null.
 */
export function useProjectResource<T>(
  fetcher: () => Promise<T>,
  fallback: T,
  deps: unknown[],
  enabled = true
): { data: T | null; notFound: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!enabled) return;

    let cancelled = false;
    setData(null);
    setNotFound(false);

    fetcher()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((error) => {
        if (cancelled) return;
        if (isNotFound(error)) {
          setNotFound(true);
        } else {
          console.error("Failed to load project resource:", error);
          setData(fallback);
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled]);

  return { data, notFound };
}
