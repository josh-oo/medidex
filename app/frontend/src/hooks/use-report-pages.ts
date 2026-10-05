import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useReportStore } from "@/hooks/use-report-store";
import type {
  GetProjectReportsParams,
  Page,
  ReportCurationDto,
  ReportFiltersState,
} from "@/types/apiDTOs";

interface UseReportPagesOptions {
  projectId: string | undefined;
  fetchReports: (projectId: string, filters: GetProjectReportsParams) => Promise<Page<ReportCurationDto>>;
  /** The parent's own unfiltered first page for this project; seeds the list and skips the first fetch. */
  initialReports: ReportCurationDto[];
  search: string;
  filters: ReportFiltersState;
  /** Called after every fresh first-page load (not for "load more"). */
  onFirstPage?: (page: Page<ReportCurationDto>, filtersActive: boolean) => void;
}

/**
 * Cursor-paginated report list for one search/filter combination. The server is always the
 * source of truth: any project/search/filter change starts over from the first page, and a
 * request id guards against slow responses landing on a list they no longer belong to.
 */
export function useReportPages({
  projectId,
  fetchReports,
  initialReports,
  search,
  filters,
  onFirstPage,
}: UseReportPagesOptions) {
  const addReports = useReportStore((state) => state.addReports);
  const [reports, setReports] = useState<ReportCurationDto[]>(initialReports);
  const [isLoading, setIsLoading] = useState(false);
  // Cursor for the next page of the *current* search/filter combination - reset to null
  // whenever that combination changes, since a cursor from one filter set is meaningless
  // against another.
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  // Every effect/handler that starts a fetch bumps this first and checks it's still current
  // before applying the result.
  const requestIdRef = useRef(0);

  // The parent layout already fetched the unfiltered first page for this project, so the
  // first effect run below skips refetching it; any later filter/search change fetches.
  const seededProjectIdRef = useRef(projectId);

  // Keep the latest callback without making it an effect dependency (selecting a report
  // must not refetch).
  const onFirstPageRef = useRef(onFirstPage);
  onFirstPageRef.current = onFirstPage;

  // A project switch swaps in the new project's own initial data right away, rather than
  // showing the previous project's reports until the fetch below resolves.
  useEffect(() => {
    requestIdRef.current += 1;
    setReports(initialReports);
    setNextCursor(null);
  }, [projectId, initialReports]);

  useEffect(() => {
    if (!projectId) return;

    const filtersActive = Boolean(search) || Object.keys(filters).length > 0;
    if (!filtersActive && seededProjectIdRef.current === projectId) {
      seededProjectIdRef.current = undefined;
      return;
    }
    seededProjectIdRef.current = undefined;

    const requestId = ++requestIdRef.current;
    let cancelled = false;
    setIsLoading(true);

    fetchReports(projectId, { search: search || undefined, ...filters })
      .then((page) => {
        if (cancelled || requestIdRef.current !== requestId) return;
        setReports(page.items);
        setNextCursor(page.nextCursor);
        addReports(page.items);
        onFirstPageRef.current?.(page, filtersActive);
      })
      .catch((error) => {
        console.error("Error fetching reports:", error);
        if (!cancelled && requestIdRef.current === requestId) {
          setReports([]);
          setNextCursor(null);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, search, filters, fetchReports, addReports]);

  const loadMore = useCallback(() => {
    if (!projectId || !nextCursor || isLoadingMore) return;

    const requestId = requestIdRef.current;
    setIsLoadingMore(true);

    fetchReports(projectId, { search: search || undefined, ...filters, cursor: nextCursor })
      .then((page) => {
        // A filter/search/project change since this request started means the list it would
        // append to no longer belongs to the current view - drop it.
        if (requestIdRef.current !== requestId) return;
        setReports((prev) => [...prev, ...page.items]);
        setNextCursor(page.nextCursor);
        addReports(page.items);
      })
      .catch((error) => {
        console.error("Error fetching more reports:", error);
        toast.error("Could not load more reports. Please try again.");
      })
      .finally(() => setIsLoadingMore(false));
  }, [projectId, nextCursor, isLoadingMore, fetchReports, search, filters, addReports]);

  const patchFlag = useCallback((reportId: number, flag: string | undefined) => {
    setReports((prev) => prev.map((r) => (r.reportId === reportId ? { ...r, flag } : r)));
  }, []);

  return { reports, isLoading, isLoadingMore, hasMore: nextCursor !== null, loadMore, patchFlag };
}
