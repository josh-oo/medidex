import { useCallback, useEffect, useState, type ComponentProps, type ReactNode } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, FileX, List, PanelLeftOpen } from "lucide-react";
import { DetailsSheetProvider } from "@/context/details-sheet-context";
import { ReportNavigationProvider, useReportNavigation } from "@/context/report-navigation-context";
import { WorkbenchAsideProvider } from "@/context/workbench-aside-context";
import { useMediaQuery } from "@/hooks/use-media-query";
import { ReportList } from "@/components/ui/report-view/report-list";
import { ReportWidget } from "@/components/reports/report-widget";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useReportStore } from "@/hooks/use-report-store";
import { cn } from "@/lib/utils";
import type { ReportCurationDto } from "@/types/apiDTOs";

type ReportListProps = ComponentProps<typeof ReportList>;

interface ReportSplitViewProps
  extends Pick<ReportListProps, "baseUrl" | "editMode" | "filterDimensions" | "fetchReports"> {
  projectId: string;
  reports: ReportCurationDto[];
  /** Rendered next to the panels inside a DetailsSheetProvider (e.g. the study sheet). */
  sheet?: ReactNode;
  children: ReactNode;
}

const COLLAPSED_STORAGE_KEY = "medidex.report-sidebar-collapsed";
// The breakpoint (tailwind `md`) from which the report list is a sidebar rather than a drawer.
const DESKTOP_QUERY = "(min-width: 768px)";
// From these widths (tailwind `xl` / `2xl`) the workbench has two columns, with the sidebar collapsed / shown.
const TWO_COLUMNS_COLLAPSED_QUERY = "(min-width: 1280px)";
const TWO_COLUMNS_QUERY = "(min-width: 1536px)";
// A column of the two-column workbench: scrolls on its own, with room for the widgets' rounded edges and shadows.
const SCROLL_COLUMN = "min-h-0 overflow-y-auto overscroll-contain -mx-1 px-1 pb-6";

const readCollapsed = () => {
  try {
    return window.localStorage.getItem(COLLAPSED_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
};

const writeCollapsed = (collapsed: boolean) => {
  try {
    window.localStorage.setItem(COLLAPSED_STORAGE_KEY, String(collapsed));
  } catch {
    // Not remembered, e.g. in a private window.
  }
};

// Keys typed into a field are not shortcuts.
const isTypingTarget = (target: EventTarget | null) =>
  target instanceof HTMLElement &&
  (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

/**
 * The reports of a project: their titles in a collapsible sidebar (a drawer on phones), the open
 * report in the workbench next to it as widgets, with previous/next through the sidebar's reports.
 */
export function ReportSplitView({
  projectId,
  reports,
  sheet,
  children,
  ...listProps
}: ReportSplitViewProps) {
  const setReports = useReportStore((state) => state.setReports);
  const params = useParams();
  const reportId = typeof params.reportId === "string" ? Number.parseInt(params.reportId, 10) : NaN;
  const hasReport = !Number.isNaN(reportId);

  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const wideEnough = useMediaQuery(collapsed ? TWO_COLUMNS_COLLAPSED_QUERY : TWO_COLUMNS_QUERY);
  // The report and the widgets next to it (see WorkbenchAside, e.g. adding a new study) in one column, the studies in the other.
  const twoColumns = wideEnough;
  const [aside, setAside] = useState<HTMLDivElement | null>(null);

  useEffect(() => {
    setReports(reports);
  }, [reports, setReports]);

  const setCollapsedAndRemember = (value: boolean) => {
    setCollapsed(value);
    writeCollapsed(value);
  };

  const hideList = () => {
    if (window.matchMedia(DESKTOP_QUERY).matches) {
      setCollapsedAndRemember(true);
    } else {
      setDrawerOpen(false);
    }
  };

  // Without an open report the list is the page, on any screen.
  const listIsDrawer = hasReport;

  return (
    <DetailsSheetProvider>
      <ReportNavigationProvider>
        <div className="relative flex h-full min-h-0 w-full bg-canvas">
          {listIsDrawer && drawerOpen && (
            <div
              className="fixed inset-0 z-[60] bg-black/30 md:hidden"
              aria-hidden="true"
              onClick={() => setDrawerOpen(false)}
            />
          )}

          <aside
            aria-label="Reports"
            className={cn(
              "flex min-h-0 flex-col bg-canvas",
              listIsDrawer
                ? cn(
                    "fixed inset-y-0 left-0 z-[61] w-[min(22rem,85vw)] shadow-xl transition-transform duration-200 motion-reduce:transition-none",
                    "md:static md:z-auto md:w-72 md:translate-x-0 md:shadow-none lg:w-80",
                    drawerOpen ? "translate-x-0" : "-translate-x-full",
                    collapsed && "md:hidden"
                  )
                : cn("w-full md:w-72 lg:w-80", collapsed && "md:hidden")
            )}
          >
            <ReportList
              {...listProps}
              initialReports={reports}
              onSelect={() => setDrawerOpen(false)}
              onCollapse={hideList}
              collapseOnDesktopOnly={!hasReport}
            />
          </aside>

          {/* In two columns the page itself stands still and each column scrolls on its own. */}
          <main
            className={cn(
              "relative min-h-0 min-w-0 flex-1",
              twoColumns ? "flex flex-col overflow-hidden" : "overflow-y-auto",
              // On phones the list is the page while no report is open.
              !hasReport && (twoColumns ? "hidden md:flex" : "hidden md:block")
            )}
          >
            <div
              className={cn(
                "mx-auto w-full max-w-[1400px] px-3 sm:px-5",
                twoColumns ? "flex min-h-0 flex-1 flex-col" : "pb-6"
              )}
            >
              {hasReport ? (
                <ReportPager
                  baseUrl={listProps.baseUrl}
                  projectId={projectId}
                  reportId={reportId}
                  showExpand={collapsed}
                  onExpand={() => setCollapsedAndRemember(false)}
                  onOpenDrawer={() => setDrawerOpen(true)}
                />
              ) : (
                // The pager's place (and its button to show the list again), so nothing moves without a report.
                <div className="-mx-3 mb-1 flex h-12 items-center gap-1 px-3 py-2 sm:-mx-5 sm:px-5">
                  {collapsed && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      className="hidden text-muted-foreground md:inline-flex"
                      aria-label="Show report list"
                      onClick={() => setCollapsedAndRemember(false)}
                    >
                      <PanelLeftOpen className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              )}
              <WorkbenchAsideProvider value={twoColumns ? aside : null}>
                <div
                  className={cn(
                    "grid items-start gap-4",
                    twoColumns && "min-h-0 flex-1 grid-cols-[minmax(0,2fr)_minmax(0,3fr)] items-stretch"
                  )}
                >
                  {hasReport ? (
                    <>
                      <div className={cn("min-w-0 space-y-4", twoColumns && SCROLL_COLUMN)}>
                        <ReportWidget reportId={reportId} editMode={listProps.editMode} />
                        {twoColumns && <div ref={setAside} className="space-y-4 empty:hidden" />}
                      </div>
                      <div className={cn("min-w-0", twoColumns && SCROLL_COLUMN)}>{children}</div>
                    </>
                  ) : (
                    // No report matches the list's search and filters (a report opens on its own otherwise).
                    <WorkbenchPlaceholder />
                  )}
                </div>
              </WorkbenchAsideProvider>
            </div>
          </main>
        </div>
        {sheet}
      </ReportNavigationProvider>
    </DetailsSheetProvider>
  );
}

interface ReportPagerProps {
  baseUrl: string;
  projectId: string;
  reportId: number;
  /** The sidebar is collapsed, so the pager offers to show it again. */
  showExpand: boolean;
  onExpand: () => void;
  onOpenDrawer: () => void;
}

/** The position of the open report in the sidebar list, with previous/next (also K/J). */
function ReportPager({ baseUrl, projectId, reportId, showExpand, onExpand, onOpenDrawer }: ReportPagerProps) {
  const { reportIds, hasMore, loadMore } = useReportNavigation();
  const navigate = useNavigate();
  const { search } = useLocation();
  const index = reportIds.indexOf(reportId);
  const previousId = index > 0 ? reportIds[index - 1] : null;
  const nextId = index >= 0 && index < reportIds.length - 1 ? reportIds[index + 1] : null;
  // The last loaded report, with more to load: "next" loads them first.
  const canLoadNext = index >= 0 && nextId === null && hasMore;

  const goTo = useCallback(
    (id: number | null) => {
      if (id !== null) navigate(`/${baseUrl}/${projectId}/${id}${search}`);
    },
    [navigate, baseUrl, projectId, search]
  );

  const goNext = useCallback(() => {
    if (nextId !== null) goTo(nextId);
    else if (canLoadNext) loadMore();
  }, [nextId, canLoadNext, goTo, loadMore]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) return;
      // Not behind an open dialog or menu.
      if (document.querySelector('[role="dialog"], [role="alertdialog"], [role="menu"]')) return;
      if (event.key === "j") goNext();
      else if (event.key === "k") goTo(previousId);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [goNext, goTo, previousId]);

  return (
    <div className="sticky top-0 z-10 -mx-3 mb-1 flex items-center gap-1 bg-canvas/85 px-3 py-2 backdrop-blur sm:-mx-5 sm:px-5">
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        className="text-muted-foreground md:hidden"
        aria-label="Show reports"
        onClick={onOpenDrawer}
      >
        <List className="h-4 w-4" />
      </Button>
      {showExpand && (
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          className="hidden text-muted-foreground md:inline-flex"
          aria-label="Show report list"
          onClick={onExpand}
        >
          <PanelLeftOpen className="h-4 w-4" />
        </Button>
      )}

      <span className="px-1 text-xs text-muted-foreground tabular-nums">
        {index >= 0 ? `Report ${index + 1} of ${reportIds.length}${hasMore ? "+" : ""}` : `Report #${reportId}`}
      </span>

      <TooltipProvider>
        <div className="ml-auto flex items-center">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="text-muted-foreground"
                aria-label="Previous report"
                disabled={previousId === null}
                onClick={() => goTo(previousId)}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Previous report (K)</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="text-muted-foreground"
                aria-label="Next report"
                disabled={nextId === null && !canLoadNext}
                onClick={goNext}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Next report (J)</TooltipContent>
          </Tooltip>
        </div>
      </TooltipProvider>
    </div>
  );
}

// A still bar standing in for a line of text.
function Bar({ className }: { className: string }) {
  return <div className={cn("h-3 rounded-full bg-muted", className)} />;
}

/** The workbench without a report: its widgets as empty outlines, the size of a real one. */
function WorkbenchPlaceholder() {
  return (
    <>
      <div className="min-w-0 space-y-4">
        <div className="rounded-2xl border bg-card p-4 shadow-xs sm:p-5">
          <div className="mb-3 flex items-center gap-2">
            <FileX className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">No report</h3>
          </div>
          <p className="text-sm text-muted-foreground">No report matches the current search and filters.</p>
          <div className="mt-5 space-y-2.5" aria-hidden="true">
            <Bar className="w-11/12" />
            <Bar className="w-3/4" />
            <Bar className="w-1/3" />
            <div className="pt-2 space-y-2">
              <Bar className="w-full" />
              <Bar className="w-full" />
              <Bar className="w-5/6" />
            </div>
          </div>
        </div>
      </div>
      <div className="min-w-0 space-y-4" aria-hidden="true">
        <div className="rounded-2xl border bg-card p-4 shadow-xs sm:p-5">
          <Bar className="mb-4 w-28" />
          <div className="h-9 rounded-md bg-muted/60" />
        </div>
        <div className="rounded-2xl border bg-card p-4 shadow-xs sm:p-5">
          <Bar className="mb-4 w-32" />
          <div className="space-y-2">
            {Array.from({ length: 4 }, (_, index) => (
              <div key={index} className="flex items-center gap-3 rounded-xl bg-muted/40 p-3">
                <div className="h-10 w-10 shrink-0 rounded-full border-[3px] border-muted" />
                <div className="min-w-0 flex-1 space-y-2">
                  <Bar className="w-2/5" />
                  <Bar className="w-4/5" />
                </div>
                <div className="h-8 w-24 shrink-0 rounded-full bg-muted/70" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
