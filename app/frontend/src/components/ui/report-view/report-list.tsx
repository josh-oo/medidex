import { useState, useMemo, useEffect, useRef } from "react";
import {
  FileText,
  Calendar,
  ChevronDown,
  Users,
  Download,
  ExternalLink,
  Flag,
  FlagOff,
  MoreVertical,
  Sparkles,
  Search,
  X,
} from "lucide-react";
import { useParams, useNavigate } from "react-router-dom";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ReportAssignedStudiesBadges } from "@/components/ui/study-view/report-assigned-studies-badges";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useGenAIEvaluationStore } from "@/hooks/use-genai-evaluation-store";
import { useReportStore } from "@/hooks/use-report-store";
import { FilterMode, GetProjectReportsParams, ProjectReportDto, ReportFilterDimension, ReportFiltersState, ProjectReportPageDto } from "@/types/apiDTOs";
import { toast } from "sonner";
import { Abstract } from "./report-abstract";
import {
  getReportFlagByReportId,
  upsertReportFlagByReportId,
  deleteReportFlagByReportId,
  getReportPdf,
} from "@/lib/api/reportApi";

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

interface ReportListProps {
  baseUrl: string;
  editMode: boolean;
  filterDimensions?: ReportFilterDimension[];
  queryParams?: Record<string, string | number | boolean | undefined>;
  // Which endpoint backs this view (getProjectReports / getProjectReportsIntake /
  // getProjectReportsReview) - each bakes in its own readiness/scope rules server-side, so
  // this component never needs to know or override those.
  fetchReports: (
    projectId: string,
    filters: GetProjectReportsParams
  ) => Promise<ProjectReportPageDto>;
  // The parent layout's own initial, unfiltered fetch (same endpoint as `fetchReports` with no
  // filters/search) - used only to seed the very first render so the list doesn't flash empty
  // while that same data is re-fetched below; every filter/search change after that always goes
  // through fetchReports, never falls back to a cached snapshot.
  initialReports: ProjectReportDto[];
}

export function ReportList({
  baseUrl,
  queryParams = { },
  editMode,
  filterDimensions = [],
  fetchReports,
  initialReports,
}: ReportListProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [filters, setFilters] = useState<ReportFiltersState>({});
  const [flagDialogOpen, setFlagDialogOpen] = useState(false);
  const [selectedFlagReport, setSelectedFlagReport] = useState<{ id: number; title: string } | null>(null);
  const [flagDetails, setFlagDetails] = useState("");
  const [flagVisibility, setFlagVisibility] = useState<"private" | "public">("private");
  const [isSubmittingFlag, setIsSubmittingFlag] = useState(false);
  const [isDeletingFlagReportId, setIsDeletingFlagReportId] = useState<number | null>(null);
  const params = useParams();
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

  const selectedCardRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (selectedReportId !== null && selectedCardRef.current) {
      selectedCardRef.current.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }
  }, [selectedReportId]);

  const storeResults = useGenAIEvaluationStore((state) => state.results);
  const runningEvaluations = useGenAIEvaluationStore((state) => state.runningEvaluations);

  const setReportFlag = useReportStore((state) => state.setFlag);
  const addReports = useReportStore((state) => state.addReports);

  // Seeded from the parent layout's own initial fetch so the list doesn't flash empty while
  // the (functionally identical) fetch below is still in flight.
  const [filteredReports, setFilteredReports] = useState<ProjectReportDto[]>(initialReports);
  const [isLoading, setIsLoading] = useState(false);
  const [debouncedSearch, setDebouncedSearch] = useState("");
  // Cursor for the next page of the *current* search/filter combination - reset to null
  // whenever that combination changes, since a cursor from one filter set is meaningless
  // against another.
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  // Only the free-text search is debounced (it fires on every keystroke); a filter chip click
  // is already a single, deliberate action, so it fetches immediately below instead of also
  // waiting out a debounce window on top of the network round trip.
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => clearTimeout(handle);
  }, [searchQuery]);

  // Guards against a slow handleLoadMore response landing after a newer filter/search/project
  // fetch has already replaced the list it was appending to - every effect/handler below that
  // starts a fetch bumps this first and checks it's still current before applying the result.
  const requestIdRef = useRef(0);

  // A project switch swaps in the new project's own initial data right away, same as on
  // first mount, rather than showing the previous project's reports until the fetch below
  // (also triggered by the projectId change) resolves.
  useEffect(() => {
    requestIdRef.current += 1;
    setFilteredReports(initialReports);
    setNextCursor(null);
  }, [projectId, initialReports]);

  // Always the single source of truth for what's rendered - no separate "use the client store's
  // snapshot when no filter is active" path, so clearing a filter/search always re-fetches
  // from the server instead of silently falling back to a possibly-stale local cache. Always
  // fetches the first page - a filter/search change starts pagination over, it never resumes
  // from wherever the previous combination's cursor left off.
  useEffect(() => {
    if (!projectId) {
      return;
    }

    const requestId = ++requestIdRef.current;
    let cancelled = false;
    setIsLoading(true);

    fetchReports(projectId, {
      search: debouncedSearch || undefined,
      ...filters,
    })
      .then((result) => {
        if (cancelled || requestIdRef.current !== requestId) return;
        setFilteredReports(result.items);
        setNextCursor(result.nextCursor);
        addReports(result.items);
      })
      .catch((error) => {
        console.error("Error fetching reports:", error);
        if (!cancelled && requestIdRef.current === requestId) {
          setFilteredReports([]);
          setNextCursor(null);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, debouncedSearch, filters, fetchReports, addReports]);

  const handleLoadMore = () => {
    if (!projectId || !nextCursor || isLoadingMore) {
      return;
    }

    const requestId = requestIdRef.current;
    setIsLoadingMore(true);

    fetchReports(projectId, {
      search: debouncedSearch || undefined,
      ...filters,
      cursor: nextCursor,
    })
      .then((result) => {
        // A filter/search/project change since this request started means the list it would
        // append to no longer belongs to the current view - drop it rather than corrupt the
        // new list with reports (and a cursor) from a stale filter combination.
        if (requestIdRef.current !== requestId) return;
        setFilteredReports((prev) => [...prev, ...result.items]);
        setNextCursor(result.nextCursor);
        addReports(result.items);
      })
      .catch((error) => {
        console.error("Error fetching more reports:", error);
        toast.error("Could not load more reports. Please try again.");
      })
      .finally(() => {
        setIsLoadingMore(false);
      });
  };

  const patchFilteredReportFlag = (reportId: number, flag: string | undefined) => {
    setFilteredReports((prev) =>
      prev.map((r) => (r.reportId === reportId ? { ...r, flag } : r))
    );
  };

  useEffect(() => {
    if (!flagDialogOpen || !selectedFlagReport) {
      return;
    }

    let cancelled = false;

    const loadExistingFlag = async () => {
      try {
        const payload = await getReportFlagByReportId(selectedFlagReport.id);

        if (cancelled) {
          return;
        }

        if (payload && typeof payload.message === "string") {
          setFlagDetails(payload.message);
          setFlagVisibility(payload.public ? "public" : "private");
          return;
        }

        setFlagDetails("");
        setFlagVisibility("private");
      } catch (error) {
        console.error("Error fetching report flag:", error);
        if (cancelled) {
          return;
        }
        setFlagDetails("");
        setFlagVisibility("private");
      }
    };

    void loadExistingFlag();

    return () => {
      cancelled = true;
    };
  }, [flagDialogOpen, selectedFlagReport]);

  const handleFlagDialogChange = (open: boolean) => {
    setFlagDialogOpen(open);
    if (!open) {
      setFlagDetails("");
      setFlagVisibility("private");
      setSelectedFlagReport(null);
    }
  };

  const handleOpenFlagDialog = (reportId: number, reportTitle: string) => {
    setFlagDetails("");
    setFlagVisibility("private");
    setSelectedFlagReport({ id: reportId, title: reportTitle });
    setFlagDialogOpen(true);
  };

  const handleSubmitFlag = async () => {
    if (!selectedFlagReport) {
      return;
    }

    if (!flagDetails.trim()) {
      toast.error("Please add a short description before submitting.");
      return;
    }

    setIsSubmittingFlag(true);
    try {
      await upsertReportFlagByReportId(selectedFlagReport.id, {
        message: flagDetails.trim(),
        public: flagVisibility === "public",
      });

      setReportFlag(selectedFlagReport.id, flagDetails.trim());
      patchFilteredReportFlag(selectedFlagReport.id, flagDetails.trim());

      toast.success("Flag saved.");
      handleFlagDialogChange(false);
    } catch (error) {
      console.error("Error submitting report flag:", error);
      toast.error("Could not submit your report. Please try again.");
    } finally {
      setIsSubmittingFlag(false);
    }
  };

  const handleDeleteFlag = async (reportId: number) => {
    setIsDeletingFlagReportId(reportId);
    try {
      await deleteReportFlagByReportId(reportId);

      setReportFlag(reportId, undefined);
      patchFilteredReportFlag(reportId, undefined);
      toast.success("Flag deleted.");

      if (selectedFlagReport?.id === reportId) {
        handleFlagDialogChange(false);
      }
    } catch (error) {
      console.error("Error deleting report flag:", error);
      toast.error("Could not delete your flag. Please try again.");
    } finally {
      setIsDeletingFlagReportId(null);
    }
  };

  const handleDownloadReportPdf = async (
  reportId: number,
  reportTitle: string
) => {
  try {
    // 1. Create a strictly Latin title to match the server request
    const safeTitle = reportTitle
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "") // Remove accents
      .replace(/[\u2010-\u2015]/g, "-") // Normalize dashes (Fixes your index 88 crash)
      .replace(/[\\/:*?"<>|]+/g, "-")   // Remove illegal filename characters
      .replace(/[^ -~]/g, "")           // Strip any remaining non-Latin/Unicode characters
      .trim();

    // 2. Fetch the PDF with auth attached
    const buffer = await getReportPdf(reportId);
    const blob = new Blob([buffer], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    
    // 3. Trigger the safe download
    link.download = `${reportId} - ${safeTitle || "report"}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Error downloading report PDF:", error);
    toast.error("Could not download PDF. Please try again.");
  }
};

  const handleOpenReportPdf = async (reportId: number) => {
    // Open the tab synchronously (still tied to the user gesture) so
    // browsers don't treat the later navigation as a blocked popup.
    // Note: "noopener" makes window.open() return null, which would
    // leave us with no reference to navigate once the PDF is fetched.
    const newTab = window.open("", "_blank");
    try {
      const buffer = await getReportPdf(reportId);
      const blob = new Blob([buffer], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      if (newTab) {
        // Navigating a popup's top-level location to a blob: URL renders
        // blank in some browsers (Safari in particular); embedding it in
        // the popup's own document works reliably everywhere instead.
        newTab.document.title = `Report ${reportId}`;
        const style = newTab.document.createElement("style");
        style.textContent = "html,body,embed{margin:0;height:100%;width:100%}";
        newTab.document.head.appendChild(style);
        const embed = newTab.document.createElement("embed");
        embed.src = url;
        embed.type = "application/pdf";
        newTab.document.body.appendChild(embed);
        newTab.focus();
      }
    } catch (error) {
      console.error("Error opening report PDF:", error);
      toast.error("Could not open PDF. Please try again.");
      newTab?.close();
    }
  };

  return (
    <div className="h-full flex flex-col pt-5">
      <div className="px-4 pb-4 border-b border-border">
        <div className="flex items-center gap-2">
          <FileText className="h-6 w-6 text-primary" />
          <h2 className="text-xl font-semibold">Reports</h2>
          <span className="text-sm text-muted-foreground">
            ({filteredReports.length}{nextCursor ? "+" : ""})
          </span>
          {isLoading && <Spinner className="h-3.5 w-3.5 text-muted-foreground" />}
        </div>

        <div className="mt-4 space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search reports..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-8"
              />
              {searchQuery && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6 p-0"
                  onClick={() => setSearchQuery("")}
                >
                  <X className="h-3 w-3" />
                </Button>
              )}
            </div>

            <div className="flex items-center gap-1.5 flex-wrap shrink-0">
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
                        variant={mode === "any" ? "outline" : "default"}
                        size="sm"
                        className="h-7 gap-1 text-xs px-3"
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
          </div>
        </div>
      </div>

      <ScrollArea className="flex-1 h-0" viewportClassName="px-4 overflow-visible">
        <div className="space-y-3 pb-4">
          {filteredReports.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="font-medium">No reports found</p>
              {searchQuery && (
                <p className="text-sm mt-1">Try adjusting your search query</p>
              )}
            </div>
          ) : (
            filteredReports.map((report, idx) => {
              const displayDate = report.year
                ? report.year.toString()
                : null;

              const hasAbstract = report.abstract && report.abstract.length > 0;
              const isSelected = selectedReportId === report.reportId;
              const isExpanded = isSelected && hasAbstract;
              const isRunningEvaluation = runningEvaluations.includes(report.reportId);
              const reportResults = storeResults[report.reportId];
              const resultCount = reportResults ? Object.keys(reportResults).length : 0;
              const flagMessage = report.flag?.trim() ?? "";
              const hasFlag = Boolean(flagMessage);
              const params = new URLSearchParams(
                Object.entries({ ...queryParams })
                  .filter(([_, v]) => v !== undefined)
                  .map(([k, v]) => [k, String(v)])
              ).toString();
              const reportHref = `/${baseUrl}/${projectId}/${report.reportId}${params ? `?${params}` : ""}`;

              if (!reportHref) {
                return null;
              }

              return (
                <div key={report.reportId || idx} className="relative">
                  <div
                    ref={isSelected ? selectedCardRef : undefined}
                    tabIndex={0}
                    role="link"
                    aria-selected={isSelected}
                    onClick={() => navigate(reportHref)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        navigate(reportHref);
                      }
                    }}
                    className={`rounded-lg border bg-card hover:border-primary/20 transition-all first:mt-3 scroll-mt-4 cursor-pointer focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary/60 ${
                      isSelected
                        ? "border-primary bg-primary/5 outline outline-2 outline-primary/40"
                        : ""
                    }`}
                  >
                    <div className="p-4">
                      <div className="relative mb-2.5 pr-9">
                        <h3 className="min-w-0 text-sm font-semibold leading-snug text-foreground">
                          {editMode &&
                            (isRunningEvaluation ? (
                              <Spinner className="mr-1 inline h-3 w-3 text-primary" />
                            ) : resultCount > 0 ? (
                              <Sparkles className="mr-1 inline h-3 w-3" />
                            ) : null)}
                          {report.title}
                        </h3>
                        <div
                          className={`absolute right-0 top-0 inline-flex items-center gap-1 ${
                            isSelected ? "opacity-100" : "opacity-0 pointer-events-none"
                          }`}
                          aria-hidden={!isSelected}
                        >
                          {report.hasPdf && (
                            <DropdownMenu>
                              <DropdownMenuTrigger asChild>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  disabled={!isSelected}
                                  className="h-8 w-8 shrink-0 text-muted-foreground"
                                  aria-label={`More actions for ${report.title}`}
                                  onClick={(e) => e.stopPropagation()}
                                >
                                  <MoreVertical className="h-4 w-4" />
                                </Button>
                              </DropdownMenuTrigger>
                              <DropdownMenuContent
                                align="end"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <DropdownMenuItem
                                  onSelect={() => {
                                    void handleOpenReportPdf(report.reportId);
                                  }}
                                >
                                  <ExternalLink className="h-4 w-4" />
                                  Open PDF
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  onSelect={() => {
                                    void handleDownloadReportPdf(
                                      report.reportId,
                                      report.title
                                    );
                                  }}
                                >
                                  <Download className="h-4 w-4" />
                                  Download PDF
                                </DropdownMenuItem>
                                {editMode && hasFlag && <DropdownMenuSeparator />}
                                {editMode && (
                                  <DropdownMenuItem
                                    onSelect={() => {
                                      handleOpenFlagDialog(report.reportId, report.title);
                                    }}
                                  >
                                    <Flag className="h-4 w-4" />
                                    {hasFlag ? "Edit flag" : "Flag report"}
                                  </DropdownMenuItem>
                                )}
                                {editMode && hasFlag && (
                                  <DropdownMenuItem
                                    disabled={isDeletingFlagReportId === report.reportId}
                                    onSelect={() => {
                                      void handleDeleteFlag(report.reportId);
                                    }}
                                  >
                                    <FlagOff className="h-4 w-4" />
                                    {isDeletingFlagReportId === report.reportId
                                      ? "Deleting flag..."
                                      : "Delete flag"}
                                  </DropdownMenuItem>
                                )}
                              </DropdownMenuContent>
                            </DropdownMenu>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-3 flex-wrap text-xs text-muted-foreground">
                        {displayDate && (
                          <div className="flex items-center gap-1.5">
                            <Calendar className="h-3.5 w-3.5 shrink-0" />
                            <span>{displayDate}</span>
                          </div>
                        )}
                        {report.authors && report.authors.length > 0 && (
                          <div className="flex items-center gap-1.5">
                            <Users className="h-3.5 w-3.5 shrink-0" />
                            <span className={isExpanded ? "" : "truncate max-w-[200px]"}>
                              {report.authors.join(", ")}
                            </span>
                          </div>
                        )}
                      </div>

                      {hasAbstract && !isExpanded && (
                        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2 mt-2">
                          {report.abstract}
                        </p>
                      )}
                      {editMode && (
                        <ReportAssignedStudiesBadges report={report} />
                      )}
                    </div>

                    {hasAbstract && isExpanded && (
                      <div className="px-4 pb-4 border-t bg-muted/30">
                        <div className="text-xs text-muted-foreground leading-relaxed mt-2 whitespace-pre-wrap">
                          <Abstract text={report.abstract}></Abstract>
                        </div>
                      </div>
                    )}

                    {editMode && hasFlag && (
                      <div className="px-4 py-2 border-t bg-muted/20 flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Flag className="h-3.5 w-3.5 text-primary" />
                        <span className="line-clamp-2">{flagMessage}</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}

          {nextCursor && (
            <div className="flex justify-center pt-1">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleLoadMore}
                disabled={isLoadingMore || isLoading}
              >
                {isLoadingMore && <Spinner className="h-3.5 w-3.5" />}
                Load more
              </Button>
            </div>
          )}
        </div>
      </ScrollArea>

      {editMode && (
        <Dialog open={flagDialogOpen} onOpenChange={handleFlagDialogChange}>
        <DialogContent
          className="sm:max-w-[560px]"
          onClick={(e) => e.stopPropagation()}
        >
          <DialogHeader>
            <DialogTitle>Flag report</DialogTitle>
            <DialogDescription>
              Report issues with this item so your team can review it.
            </DialogDescription>
          </DialogHeader>

          {selectedFlagReport && (
            <div className="space-y-4">
              <div className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">Report:</span>{" "}
                {selectedFlagReport.title}
              </div>

              <div className="space-y-2">
                <label htmlFor="flag-details" className="text-sm font-medium">
                  Details
                </label>
                <Textarea
                  id="flag-details"
                  value={flagDetails}
                  onChange={(e) => setFlagDetails(e.target.value)}
                  placeholder="Tell us what is wrong with this report..."
                  className="h-28 min-h-28 resize-none"
                />
              </div>

              <div className="space-y-2">
                <p className="text-sm font-medium">Visibility</p>
                <RadioGroup
                  value={flagVisibility}
                  onValueChange={(value) => setFlagVisibility(value as "private" | "public")}
                  className="gap-2"
                >
                  <label
                    htmlFor="flag-visibility-private"
                    className="flex items-start gap-2 rounded-md border p-3 cursor-pointer"
                  >
                    <RadioGroupItem id="flag-visibility-private" value="private" />
                    <span className="text-sm leading-tight">
                      <span className="font-medium">Private</span>
                      <span className="block text-xs text-muted-foreground">
                        Visible to you only.
                      </span>
                    </span>
                  </label>

                  <label
                    htmlFor="flag-visibility-public"
                    className="flex items-start gap-2 rounded-md border p-3 cursor-pointer"
                  >
                    <RadioGroupItem id="flag-visibility-public" value="public" />
                    <span className="text-sm leading-tight">
                      <span className="font-medium">Public</span>
                      <span className="block text-xs text-muted-foreground">
                        Visible to you and the project owner.
                      </span>
                    </span>
                  </label>
                </RadioGroup>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleFlagDialogChange(false)}
              disabled={isSubmittingFlag}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleSubmitFlag}
              disabled={isSubmittingFlag}
            >
              {isSubmittingFlag ? "Submitting..." : "Submit"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      )}
    </div>
  );
}
