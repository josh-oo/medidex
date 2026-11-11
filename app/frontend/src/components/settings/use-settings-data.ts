import { useCallback, useEffect, useRef, useState } from "react";

// What the sections of the settings loaded last, by key, for the lifetime of the tab (signing out reloads it).
const cache = new Map<string, unknown>();

/**
 * The data of a section of the settings. A section shown before starts with what it loaded then and refreshes it
 * quietly, so browsing the sections shows no loading state; only the first visit is null until `load` resolves.
 * `load` may change between renders (the one of the latest render runs when the key changes). Errors go to `onError`
 * (the data stays as it was). The third value says whether a load is running.
 */
export function useSettingsData<T>(
  key: string,
  load: () => Promise<T>,
  onError?: (error: unknown) => void
): [T | null, (next: T | ((current: T | null) => T)) => void, boolean] {
  const [data, setState] = useState<T | null>(() => (cache.get(key) as T | undefined) ?? null);
  const [loading, setLoading] = useState(true);
  const loadRef = useRef(load);
  loadRef.current = load;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    if (cache.has(key)) setState(cache.get(key) as T);
    loadRef
      .current()
      .then((loaded) => {
        if (cancelled) return;
        cache.set(key, loaded);
        setState(loaded);
      })
      .catch((error) => {
        if (!cancelled) onErrorRef.current?.(error);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [key]);

  // Also takes an update of the current data (the cache holds the latest, e.g. after an await).
  const setData = useCallback(
    (next: T | ((current: T | null) => T)) => {
      const value =
        typeof next === "function"
          ? (next as (current: T | null) => T)((cache.get(key) as T | undefined) ?? null)
          : next;
      cache.set(key, value);
      setState(value);
    },
    [key]
  );

  return [data, setData, loading];
}
