import { Suspense, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ComponentProps, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, FileText, FileX, List, PanelLeftOpen } from "lucide-react";
import { DetailsSheetProvider } from "@/context/details-sheet-context";
import { ReportNavigationProvider, useReportNavigation } from "@/context/report-navigation-context";
import { PDF_PANE_TAB, ReportPdfPaneProvider, type ComparedStudy, type PdfFocus, type ReportPdfPaneState } from "@/context/report-pdf-pane-context";
import { WorkbenchAsideProvider } from "@/context/workbench-aside-context";
import { WorkbenchFooterProvider } from "@/context/workbench-footer-context";
import { useMediaQuery } from "@/hooks/use-media-query";
import { ReportList } from "@/components/ui/report-view/report-list";
import { ReportWidget } from "@/components/reports/report-widget";
import { ReportPdfPane } from "@/components/reports/report-pdf-pane";
import { Button } from "@/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Widget } from "@/components/ui/widget";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { useReportStore } from "@/hooks/use-report-store";
import { cn } from "@/lib/utils";
import type { Page, ReportCurationDto } from "@/types/apiDTOs";
import { PanelSkeleton, ReportListSkeleton, ReportWidgetSkeleton } from "./workbench-skeleton";

type ReportListProps = ComponentProps<typeof ReportList>;

interface ReportSplitViewProps
  extends Pick<ReportListProps, "baseUrl" | "editMode" | "filterDimensions" | "fetchReports" | "renderStatus"> {
  projectId: string;
  /** The first page of the project's reports; its cursor lets the list load the rest. */
  firstPage: Page<ReportCurationDto>;
  /** Rendered next to the panels inside a DetailsSheetProvider (e.g. the study sheet). */
  sheet?: ReactNode;
  /** The panel next to the report while it loads (see workbench-skeleton.tsx); a generic outline by default. */
  panelSkeleton?: ReactNode;
  children: ReactNode;
}

const COLLAPSED_STORAGE_KEY = "medidex.report-sidebar-collapsed";
// Where the panel group remembers how wide the workbench and the PDF pane were last.
const PDF_SPLIT_STORAGE_KEY = "medidex.report-pdf-split";
// The breakpoint (tailwind `md`) from which the report list is a sidebar rather than a drawer.
const DESKTOP_QUERY = "(min-width: 768px)";
// From these widths (tailwind `xl` / `2xl`) the workbench has two columns, with the sidebar collapsed / shown.
const TWO_COLUMNS_COLLAPSED_QUERY = "(min-width: 1280px)";
const TWO_COLUMNS_QUERY = "(min-width: 1536px)";
// The height of what the foot of the workbench shows over the columns (see WorkbenchFooter), as a CSS variable.
const FOOTER_HEIGHT = "--workbench-footer-height";
// A column of the two-column workbench: scrolls on its own, with room for the widgets' rounded edges and shadows, and
// at its end for what the foot of the workbench shows over it.
const SCROLL_COLUMN =
  "min-h-0 overflow-y-auto overscroll-contain -mx-1 px-1 pb-[calc(var(--workbench-footer-height,0px)+1.5rem)]";
// The workbench and the docked pane next to it are frames alike on the canvas: a header of this height over what scrolls.
const FRAME = "overflow-hidden rounded-2xl border bg-card shadow-xs";
const FRAME_HEADER = "flex h-12 shrink-0 items-center gap-1 border-b px-2 sm:px-3";

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

// Folding the sidebar away or out changes the whole layout at once (the sidebar, and one or two columns). Where the
// browser can, it animates the change: every part moves from where it was to where it is now (see the
// view-transition rules in globals.css). Elsewhere, and with reduced motion, the layout changes at once; also where
// the browser cannot nest the columns in the workbench's body, which clips them (see globals.css).
const withLayoutTransition = (update: () => void) => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!document.startViewTransition || !CSS.supports("view-transition-group", "nearest") || reduceMotion) {
    update();
    return;
  }
  // The parts that move are named for the transition only (see globals.css): a name changes how an element is drawn.
  const root = document.documentElement;
  root.dataset.layoutTransition = "";
  const transition = document.startViewTransition(() => flushSync(update));
  void transition.finished.finally(() => {
    delete root.dataset.layoutTransition;
  });
};

// Whether the workbench has two columns: from a width that depends on whether the sidebar is folded away.
function useTwoColumns(collapsed: boolean) {
  // Both widths are watched, so that folding the sidebar changes the columns in the same render (and transition).
  const wideWithSidebar = useMediaQuery(TWO_COLUMNS_QUERY);
  const wideWithoutSidebar = useMediaQuery(TWO_COLUMNS_COLLAPSED_QUERY);
  return collapsed ? wideWithoutSidebar : wideWithSidebar;
}

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
  firstPage,
  sheet,
  panelSkeleton,
  children,
  ...listProps
}: ReportSplitViewProps) {
  const setReports = useReportStore((state) => state.setReports);
  const params = useParams();
  const reportId = typeof params.reportId === "string" ? Number.parseInt(params.reportId, 10) : NaN;
  const hasReport = !Number.isNaN(reportId);

  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const isDesktop = useMediaQuery(DESKTOP_QUERY);
  // The PDF of the open report, next to the workbench (on phones over it); it stays open from report to report.
  const [pdfOpen, setPdfOpen] = useState(false);
  // The PDF or an extension's tab next to it (see ReportPdfPaneState.tab).
  const [paneTab, setPaneTab] = useState(PDF_PANE_TAB);
  // The passage of the open report that a source link opened the PDF at.
  const [pdfFocus, setPdfFocus] = useState<PdfFocus | null>(null);
  // The study compared with the open report, under its PDF; a comparison belongs to the report.
  const [compared, setCompared] = useState<ComparedStudy | null>(null);
  const showPdf = pdfOpen && hasReport;
  const pdfPane = useMemo<ReportPdfPaneState>(
    () => ({
      open: showPdf,
      tab: paneTab,
      showTab: (tab) => {
        setPaneTab(tab);
        setPdfOpen(true);
      },
      focus: pdfFocus,
      setOpen: (open) => {
        setPdfOpen(open);
        if (!open) {
          setPaneTab(PDF_PANE_TAB);
          setPdfFocus(null);
          setCompared(null);
        }
      },
      show: (focus) => {
        setPaneTab(PDF_PANE_TAB);
        setPdfFocus(focus ?? null);
        setPdfOpen(true);
      },
      compared,
      compare: (study) => {
        setCompared(study);
        if (study) {
          setPaneTab(PDF_PANE_TAB);
          setPdfOpen(true);
        }
      },
    }),
    [showPdf, paneTab, pdfFocus, compared]
  );
  // The report and the widgets next to it (see WorkbenchAside, e.g. adding a new study) in one column, the studies in the
  // other; next to the PDF the workbench is too narrow for two.
  const twoColumns = useTwoColumns(collapsed) && !showPdf;
  const sidebarHidden = collapsed && isDesktop;
  const [aside, setAside] = useState<HTMLDivElement | null>(null);
  const [footer, setFooter] = useState<HTMLDivElement | null>(null);
  const workbenchRef = useRef<HTMLDivElement>(null);
  // The columns keep their ends clear of the footer over them.
  useEffect(() => {
    const workbench = workbenchRef.current;
    if (!footer || !workbench) return;
    const observer = new ResizeObserver(([entry]) =>
      workbench.style.setProperty(FOOTER_HEIGHT, `${Math.round(entry.borderBoxSize[0]?.blockSize ?? 0)}px`)
    );
    observer.observe(footer);
    return () => {
      observer.disconnect();
      workbench.style.removeProperty(FOOTER_HEIGHT);
    };
  }, [footer]);

  // Before paint, so that the report widget never shows the first frame without its report.
  useLayoutEffect(() => {
    setReports(firstPage.items);
  }, [firstPage, setReports]);

  // The next report starts at its top, in whichever of the page or the columns scrolls.
  const mainRef = useRef<HTMLDivElement>(null);
  const reportColumnRef = useRef<HTMLDivElement>(null);
  const panelColumnRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    for (const element of [mainRef.current, reportColumnRef.current, panelColumnRef.current]) {
      element?.scrollTo({ top: 0 });
    }
    // A passage belongs to its report: the next one's PDF opens at its start, and a comparison ends.
    setPdfFocus(null);
    setCompared(null);
  }, [reportId]);

  // In two columns the page stands still: a scroll it kept from one column (e.g. while the PDF was open) would shift
  // both columns up, cut off at the top and empty at the bottom.
  useLayoutEffect(() => {
    if (twoColumns) mainRef.current?.scrollTo({ top: 0 });
  }, [twoColumns]);

  const setCollapsedAndRemember = (value: boolean) => {
    writeCollapsed(value);
    withLayoutTransition(() => setCollapsed(value));
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
        <ReportPdfPaneProvider value={pdfPane}>
        <div className="relative flex h-full min-h-0 w-full bg-canvas">
          {listIsDrawer && drawerOpen && (
            <div
              className="fixed inset-0 z-[60] bg-black/30 md:hidden"
              aria-hidden="true"
              onClick={() => setDrawerOpen(false)}
            />
          )}

          {/* On desktop the sidebar folds away by its width; its content keeps its width, so nothing in it reflows. */}
          <aside
            aria-label="Reports"
            data-layout-part="report-sidebar"
            inert={sidebarHidden}
            className={cn(
              "flex min-h-0 shrink-0 flex-col overflow-hidden bg-canvas",
              "motion-reduce:transition-none",
              listIsDrawer
                ? cn(
                    "fixed inset-y-0 left-0 z-[61] w-[min(22rem,85vw)] shadow-xl transition-transform duration-200",
                    "md:static md:z-auto md:translate-x-0 md:shadow-none",
                    drawerOpen ? "translate-x-0" : "-translate-x-full"
                  )
                : "w-full",
              collapsed ? "md:w-0" : "md:w-72 lg:w-80"
            )}
          >
            <div className="flex h-full min-h-0 w-full flex-col md:w-72 lg:w-80 motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300">
              <ReportList
                {...listProps}
                initialPage={firstPage}
                onSelect={() => setDrawerOpen(false)}
                onCollapse={hideList}
                collapseOnDesktopOnly={!hasReport}
              />
            </div>
          </aside>

          {/* Always a panel group, so that opening the PDF does not remount the workbench (and lose its state). */}
          <ResizablePanelGroup
            direction="horizontal"
            autoSaveId={PDF_SPLIT_STORAGE_KEY}
            className={cn("min-w-0 flex-1 p-2 sm:p-3", !hasReport && "hidden md:flex")}
          >
          <ResizablePanel id="workbench" order={1} minSize={30}>
          {/* A frame: the pager as its header over what scrolls. */}
          <main
            data-layout-part="report-workbench"
            className={cn(
              FRAME,
              "flex h-full min-h-0 min-w-0 flex-col",
              // On phones the list is the page while no report is open.
              !hasReport && "hidden md:flex"
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
                <div className={FRAME_HEADER}>
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
          {/* In two columns this stands still and each column scrolls on its own. */}
          <div
            ref={mainRef}
            data-layout-part="report-workbench-body"
            className={cn("relative min-h-0 flex-1 bg-canvas/60", twoColumns ? "flex flex-col overflow-hidden" : "overflow-y-auto")}
          >
            <div
              ref={workbenchRef}
              className={cn(
                "mx-auto w-full max-w-[1400px] px-3 pt-3 sm:px-5 sm:pt-4",
                twoColumns ? "relative flex min-h-0 flex-1 flex-col" : "pb-6"
              )}
            >
              <WorkbenchFooterProvider value={hasReport ? footer : null}>
              <WorkbenchAsideProvider value={twoColumns ? aside : null}>
                <div
                  className={cn(
                    "grid items-start gap-4",
                    twoColumns && "min-h-0 flex-1 grid-cols-[minmax(0,2fr)_minmax(0,3fr)] items-stretch"
                  )}
                >
                  {hasReport ? (
                    <>
                      <div
                        ref={reportColumnRef}
                        data-layout-part="report-column"
                        className={cn("min-w-0 space-y-4", twoColumns && SCROLL_COLUMN)}
                      >
                        <ReportWidget reportId={reportId} editMode={listProps.editMode} />
                        {twoColumns && <div ref={setAside} className="space-y-4 empty:hidden" />}
                      </div>
                      <div
                        ref={panelColumnRef}
                        data-layout-part="study-column"
                        className={cn("min-w-0", twoColumns && SCROLL_COLUMN)}
                      >
                        {/* The report page is a lazy chunk: while it loads only this panel waits, not the list and the report. */}
                        <Suspense fallback={panelSkeleton ?? <PanelSkeleton />}>{children}</Suspense>
                      </div>
                    </>
                  ) : (
                    <EmptyWorkbench panelSkeleton={panelSkeleton} />
                  )}
                </div>
              </WorkbenchAsideProvider>
              </WorkbenchFooterProvider>
              {/* Over the foot of both columns (see WorkbenchFooter), or of the page while it scrolls as one; clicks go
                  through it to the columns, except on what it shows. */}
              <div
                ref={setFooter}
                data-layout-part="report-footer"
                className={cn(
                  "pointer-events-none z-20 empty:hidden",
                  twoColumns ? "absolute inset-x-3 bottom-0 sm:inset-x-5" : "sticky bottom-0"
                )}
              />
            </div>
          </div>
          </main>
          </ResizablePanel>
          {showPdf && isDesktop && (
            <>
              {/* In the gap between the two frames. */}
              <ResizableHandle withHandle data-layout-part="report-pdf-handle" className="w-3 bg-transparent" />
              <ResizablePanel id="pdf" order={2} defaultSize={45} minSize={25}>
                <ReportPdfPane reportId={reportId} focus={pdfFocus} docked onClose={() => pdfPane.setOpen(false)} />
              </ResizablePanel>
            </>
          )}
          </ResizablePanelGroup>

          {/* Phones have no room for a split: the PDF covers the workbench until it is closed. */}
          {showPdf && !isDesktop && (
            <div className="fixed inset-0 z-[70]">
              <ReportPdfPane reportId={reportId} focus={pdfFocus} docked={false} onClose={() => pdfPane.setOpen(false)} />
            </div>
          )}
        </div>
        </ReportPdfPaneProvider>
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
  const { reportIds, hasMore, total, loadMore } = useReportNavigation();
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
    <div className={FRAME_HEADER}>
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
        {index >= 0 ? `Report ${index + 1} of ${total ?? `${reportIds.length}${hasMore ? "+" : ""}`}` : `Report #${reportId}`}
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

/**
 * The whole report workbench while its project loads: the sidebar (unless folded away) and the outlines of the
 * widgets, where the real ones will be.
 */
export function ReportSplitViewSkeleton({ panelSkeleton }: { panelSkeleton?: ReactNode }) {
  const [collapsed] = useState(readCollapsed);
  const twoColumns = useTwoColumns(collapsed);

  return (
    <div className="flex h-full min-h-0 w-full bg-canvas" aria-busy="true">
      {!collapsed && (
        <div className="hidden w-72 shrink-0 md:block lg:w-80">
          <ReportListSkeleton />
        </div>
      )}
      <div className="min-h-0 min-w-0 flex-1 p-2 sm:p-3">
        <div className={cn(FRAME, "flex h-full flex-col")}>
          {/* The pager's place. */}
          <div className={FRAME_HEADER} />
          <div className="min-h-0 flex-1 overflow-hidden bg-canvas/60">
            <div className="mx-auto w-full max-w-[1400px] px-3 pt-3 sm:px-5 sm:pt-4">
              <div className={cn("grid items-start gap-4", twoColumns && "grid-cols-[minmax(0,2fr)_minmax(0,3fr)]")}>
                <WorkbenchSkeleton panelSkeleton={panelSkeleton} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** The two columns of the workbench as outlines: the report, and the panel next to it. */
function WorkbenchSkeleton({ panelSkeleton }: { panelSkeleton?: ReactNode }) {
  return (
    <>
      <div className="min-w-0 space-y-4">
        <Widget title="Report" icon={FileText}>
          <ReportWidgetSkeleton />
        </Widget>
      </div>
      <div className="min-w-0">{panelSkeleton ?? <PanelSkeleton />}</div>
    </>
  );
}

/**
 * The workbench without an open report. While the list loads, or is about to open its first report (see ReportList),
 * the outlines of that report; the placeholder only when no report matches the list's search and filters.
 */
function EmptyWorkbench({ panelSkeleton }: { panelSkeleton?: ReactNode }) {
  const { reportIds, isLoading } = useReportNavigation();
  if (isLoading || reportIds.length > 0) return <WorkbenchSkeleton panelSkeleton={panelSkeleton} />;
  return <WorkbenchPlaceholder />;
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
