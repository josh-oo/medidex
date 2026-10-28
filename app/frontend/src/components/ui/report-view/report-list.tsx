import { useState, useMemo, useEffect, useRef } from "react";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useReportPages } from "@/hooks/use-report-pages";
import { useClientPages } from "@/hooks/use-client-pages";
import { Pager } from "@/components/ui/pager";
import { FileText, ChevronDown, PanelLeftClose, Search, X } from "lucide-react";
import { useParams, useNavigate, useLocation } from "react-router-dom";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ReportStatusSlot } from "@/context/study-report-slots-context";
import { useReportNavigation } from "@/context/report-navigation-context";
import { useReportStore } from "@/hooks/use-report-store";
import { cn } from "@/lib/utils";
import { isNewStudyAssignment } from "@/lib/study-assignment";
import { FilterMode, GetProjectReportsParams, ReportCurationDto, ReportFilterDimension, ReportFiltersState, Page } from "@/types/apiDTOs";

function reportFilterMode(filters: ReportFiltersState, field: keyof ReportFiltersState): FilterMode {
  return filters[field] ?? "any";
}

// Each dimension's 3 states (Any/Only/Exclude) are independent of every other dimension's -
// setting one never touches another field.
function setReportFilterMode(
  filters: ReportFiltersState,
  field: keyof ReportFiltersState,
  mode: FilterMode
): ReportFiltersState {
  if (mode === "any") {
    const next = { ...filters };
    delete next[field];
    return next;
  }
  return { ...filters, [field]: mode };
}

// The open report is this close to the end of the loaded list before the next page loads, so
// paging through the reports in the workbench never runs into the end of a page.
const PREFETCH_DISTANCE = 3;
// Report titles shown per page of the list.
const LIST_PAGE_SIZE = 25;

interface ReportListProps {
  baseUrl: string;
  editMode: boolean;
  filterDimensions?: ReportFilterDimension[];
  // Which endpoint backs this view (getProjectReports / getProjectReportsIntake /
  // getProjectReportsReview) - each bakes in its own readiness/scope rules server-side, so
  // this component never needs to know or override those.
  fetchReports: (
    projectId: string,
    filters: GetProjectReportsParams
  ) => Promise<Page<ReportCurationDto>>;
  // The parent layout's own initial, unfiltered fetch (same endpoint as `fetchReports` with no
  // filters/search) - used only to seed the very first render so the list doesn't flash empty
  // while that same data is re-fetched below; every filter/search change after that always goes
  // through fetchReports, never falls back to a cached snapshot.
  initialReports: ReportCurationDto[];
  /** Called after a report was picked (e.g. to close the list on phones). */
  onSelect?: () => void;
  /** Shows a button that hides the list. */
  onCollapse?: () => void;
  /** The button only shows from the sidebar breakpoint on (e.g. on phones the list is the page itself). */
  collapseOnDesktopOnly?: boolean;
}

/** The reports of a project as a list of titles, the sidebar of the report workbench. */
export function ReportList({
  baseUrl,
  editMode,
  filterDimensions = [],
  fetchReports,
  initialReports,
  onSelect,
  onCollapse,
  collapseOnDesktopOnly = false,
}: ReportListProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [filters, setFilters] = useState<ReportFiltersState>({});
  const params = useParams();
  const { search: locationSearch } = useLocation();
  const projectId =
    typeof params.projectId === "string"
      ? params.projectId
      : undefined;

  const reportIdParam =
    typeof params.reportId === "string"
      ? params.reportId
      : Array.isArray(params.reportId)
      ? params.reportId[0]
      : undefined;

  const selectedReportId = useMemo(() => {
    if (!reportIdParam) {
      return null;
    }
    const parsed = Number.parseInt(reportIdParam, 10);
    return Number.isNaN(parsed) ? null : parsed;
  }, [reportIdParam]);

  const selectedCardRef = useRef<HTMLButtonElement | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (selectedReportId !== null && selectedCardRef.current) {
      selectedCardRef.current.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
    }
  }, [selectedReportId]);

  const debouncedSearch = useDebouncedValue(searchQuery.trim(), 300);
  const storedReports = useReportStore((state) => state.reports);

  const {
    reports: filteredReports,
    isLoading,
    isLoadingMore,
    hasMore,
    loadMore: handleLoadMore,
  } = useReportPages({
    projectId,
    fetchReports,
    initialReports,
    search: debouncedSearch,
    filters,
    onFirstPage: (page, filtersActive) => {
      // The open report fell out of the filtered list (only decidable once the whole
      // result is in, i.e. no further page) - drop it from the URL too.
      if (
        filtersActive &&
        selectedReportId !== null &&
        page.nextCursor === null &&
        !page.items.some((r) => r.reportId === selectedReportId)
      ) {
        navigate(`/${baseUrl}/${projectId}${locationSearch}`, { replace: true });
      }
    },
  });

  // Hands the list order to the workbench's previous/next. The ref keeps the published loadMore
  // stable, so publishing doesn't loop through the context.
  const { setNavigation } = useReportNavigation();
  const loadMoreRef = useRef(handleLoadMore);
  loadMoreRef.current = handleLoadMore;
  const reportIdsKey = filteredReports.map((report) => report.reportId).join(",");
  useEffect(() => {
    setNavigation({
      reportIds: reportIdsKey ? reportIdsKey.split(",").map(Number) : [],
      hasMore,
      loadMore: () => loadMoreRef.current(),
    });
  }, [reportIdsKey, hasMore, setNavigation]);

  const selectedIndex = filteredReports.findIndex((report) => report.reportId === selectedReportId);

  // A report is always open: without one (the project's page itself, or the open one was filtered
  // out), the first of the list opens in its place.
  const firstReportId = filteredReports[0]?.reportId;
  useEffect(() => {
    if (selectedReportId === null && firstReportId !== undefined && !isLoading) {
      navigate(`/${baseUrl}/${projectId}/${firstReportId}${locationSearch}`, { replace: true });
    }
  }, [selectedReportId, firstReportId, isLoading, navigate, baseUrl, projectId, locationSearch]);
  const listPages = useClientPages({
    items: filteredReports,
    pageSize: LIST_PAGE_SIZE,
    hasMore,
    loadMore: handleLoadMore,
    resetKey: `${projectId}|${debouncedSearch}|${JSON.stringify(filters)}`,
  });
  // The page follows the open report, e.g. when the workbench pages past the end of this one.
  const { setPage } = listPages;
  useEffect(() => {
    if (selectedIndex >= 0) setPage(Math.floor(selectedIndex / LIST_PAGE_SIZE));
  }, [selectedIndex, setPage]);
  useEffect(() => {
    if (
      selectedIndex >= 0 &&
      selectedIndex >= filteredReports.length - PREFETCH_DISTANCE &&
      hasMore &&
      !isLoadingMore &&
      !isLoading
    ) {
      handleLoadMore();
    }
  }, [selectedIndex, filteredReports.length, hasMore, isLoadingMore, isLoading, handleLoadMore]);

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 pt-4 pb-3 space-y-3">
        <div className="flex items-center gap-2 px-1">
          <h2 className="text-base font-semibold tracking-tight">Reports</h2>
          <span className="text-sm text-muted-foreground tabular-nums">
            {filteredReports.length}{hasMore ? "+" : ""}
          </span>
          {isLoading && <Spinner className="h-3.5 w-3.5 text-muted-foreground" />}
          {onCollapse && (
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              className={cn("ml-auto text-muted-foreground", collapseOnDesktopOnly && "hidden md:inline-flex")}
              aria-label="Hide report list"
              onClick={onCollapse}
            >
              <PanelLeftClose className="h-4 w-4" />
            </Button>
          )}
        </div>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search reports..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 pr-8 bg-card border-transparent shadow-xs"
          />
          {searchQuery && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label="Clear search"
              className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6 p-0"
              onClick={() => setSearchQuery("")}
            >
              <X className="h-3 w-3" />
            </Button>
          )}
        </div>

        {filterDimensions.length > 0 && (
          <div className="flex items-center gap-1 flex-wrap">
            {filterDimensions.map((dimension) => {
              const mode = reportFilterMode(filters, dimension.field);
              const currentLabel =
                mode === "only"
                  ? dimension.onlyLabel
                  : mode === "exclude"
                  ? dimension.excludeLabel
                  : dimension.label;
              return (
                <DropdownMenu key={dimension.field}>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant={mode === "any" ? "ghost" : "default"}
                      size="sm"
                      className={cn("h-7 gap-1 text-xs px-3", mode === "any" && "text-muted-foreground")}
                    >
                      {currentLabel}
                      <ChevronDown className="h-3 w-3" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start">
                    <DropdownMenuItem
                      onSelect={() =>
                        setFilters((prev) => setReportFilterMode(prev, dimension.field, "any"))
                      }
                    >
                      Any
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() =>
                        setFilters((prev) => setReportFilterMode(prev, dimension.field, "only"))
                      }
                    >
                      {dimension.onlyLabel}
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() =>
                        setFilters((prev) => setReportFilterMode(prev, dimension.field, "exclude"))
                      }
                    >
                      {dimension.excludeLabel}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              );
            })}
          </div>
        )}
      </div>

      <ScrollArea className="flex-1 h-0" viewportClassName="px-3">
        <div className="space-y-0.5 pb-4">
          {listPages.isTurning ? (
            <div className="flex justify-center py-10"><Spinner className="h-5 w-5 text-muted-foreground" /></div>
          ) : filteredReports.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileText className="h-10 w-10 mx-auto mb-3 opacity-50" />
              <p className="text-sm font-medium">No reports found</p>
              {searchQuery && (
                <p className="text-xs mt-1">Try adjusting your search query</p>
              )}
            </div>
          ) : (
            listPages.pageItems.map((report) => {
              const isSelected = selectedReportId === report.reportId;
              // The store holds links made since the list loaded.
              const assignedStudies = storedReports[report.reportId]?.assignedStudies ?? report.assignedStudies ?? [];
              const linkedToNew = assignedStudies.some((study) => isNewStudyAssignment(study.createdAt, report.createdAt));

              return (
                <button
                  key={report.reportId}
                  ref={isSelected ? selectedCardRef : undefined}
                  type="button"
                  aria-current={isSelected ? "page" : undefined}
                  onClick={() => {
                    navigate(`/${baseUrl}/${projectId}/${report.reportId}${locationSearch}`);
                    onSelect?.();
                  }}
                  className={cn(
                    "w-full flex items-start gap-2.5 rounded-xl px-3 py-2 text-left text-[13px] leading-snug transition-colors scroll-my-2 cursor-pointer",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                    isSelected
                      ? "bg-card shadow-sm font-medium text-foreground"
                      : "text-foreground/85 hover:bg-card/60"
                  )}
                >
                  {editMode && (
                    // Blue: linked to a new study, green: to an existing one; no dot while not linked.
                    <span
                      className={cn(
                        "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                        assignedStudies.length === 0
                          ? "bg-transparent"
                          : linkedToNew
                          ? "bg-blue-500"
                          : "bg-emerald-500"
                      )}
                      title={
                        assignedStudies.length === 0
                          ? undefined
                          : linkedToNew
                          ? "Linked to a new study"
                          : "Linked to an existing study"
                      }
                    />
                  )}
                  <span className="min-w-0 flex-1 line-clamp-2">
                    {editMode && <ReportStatusSlot reportId={report.reportId} />}
                    {report.title}
                  </span>
                </button>
              );
            })
          )}

          <Pager
            className="justify-center pt-2"
            range={listPages.range}
            canPrev={listPages.canPrev}
            canNext={listPages.canNext}
            onPrev={listPages.prev}
            onNext={listPages.next}
            loading={isLoadingMore}
          />
        </div>
      </ScrollArea>
    </div>
  );
}
