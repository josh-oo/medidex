import { useCallback, useEffect, useState } from "react";

interface UseClientPagesOptions<T> {
  /** Everything loaded so far, in order. */
  items: T[];
  pageSize: number;
  /** The server has more items after the loaded ones. */
  hasMore?: boolean;
  /** Loads the next batch from the server; called when paging past the loaded items. */
  loadMore?: () => void;
  /** A change starts over at the first page (e.g. another report). */
  resetKey?: unknown;
}

/**
 * Shows loaded items a page at a time. Paging past what is loaded asks for more and turns the
 * page once it arrives, so cursor-paginated lists can be paged without changing how they load.
 */
export function useClientPages<T>({ items, pageSize, hasMore = false, loadMore, resetKey }: UseClientPagesOptions<T>) {
  const [page, setPage] = useState(0);
  const [pendingNext, setPendingNext] = useState(false);

  useEffect(() => {
    setPage(0);
    setPendingNext(false);
  }, [resetKey]);

  const loadedPages = Math.max(1, Math.ceil(items.length / pageSize));
  // The list got shorter (e.g. a new search): stay on a page that exists.
  const currentPage = Math.min(page, loadedPages - 1);

  // Turns the page once the batch asked for has arrived, or gives up when there is no more.
  useEffect(() => {
    if (!pendingNext) return;
    if (items.length > (currentPage + 1) * pageSize) {
      setPage(currentPage + 1);
      setPendingNext(false);
    } else if (!hasMore) {
      setPendingNext(false);
    }
  }, [pendingNext, items.length, currentPage, pageSize, hasMore]);

  const canPrev = currentPage > 0;
  const nextLoaded = items.length > (currentPage + 1) * pageSize;
  const canNext = nextLoaded || hasMore;

  const prev = useCallback(() => setPage(Math.max(0, currentPage - 1)), [currentPage]);
  const next = useCallback(() => {
    if (nextLoaded) setPage(currentPage + 1);
    else if (hasMore && loadMore) {
      setPendingNext(true);
      loadMore();
    }
  }, [nextLoaded, hasMore, loadMore, currentPage]);

  const start = currentPage * pageSize;

  return {
    pageItems: items.slice(start, start + pageSize),
    page: currentPage,
    /** First and last position shown, 1-based. */
    range: [items.length === 0 ? 0 : start + 1, Math.min(start + pageSize, items.length)] as const,
    total: items.length,
    hasMore,
    canPrev,
    canNext,
    prev,
    next,
    setPage,
    isTurning: pendingNext,
  };
}
