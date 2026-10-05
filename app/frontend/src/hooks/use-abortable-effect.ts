import { useEffect, type DependencyList } from "react";

/**
 * Runs `load` with an AbortSignal that is aborted when `deps` change or the component
 * unmounts. `load` should check `signal.aborted` before applying results.
 */
export function useAbortableEffect(
  load: (signal: AbortSignal) => void | Promise<void>,
  deps: DependencyList
) {
  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
