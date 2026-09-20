"use client";

import { useState, useMemo, useEffect, useRef } from "react";
import {
  FileText,
  Calendar,
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
import { useParams, useRouter } from "next/navigation";
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
import { filterReports, ReportFilterType } from "@/lib/filterUtils";
import { useReportStore } from "@/hooks/use-report-store";
import { ProjectAnnotationsDto } from "@/types/apiDTOs";
import { toast } from "sonner";
import { Abstract } from "./report-abstract";

interface ReportListProps {
  baseUrl: string;
  editMode: boolean;
  filterOptions?: { value: string; label: string }[];
  queryParams?: Record<string, string | number | boolean | undefined>;
  annotations?: ProjectAnnotationsDto;
}

export function ReportList({
  baseUrl,
  queryParams = { }, 
  editMode,
  filterOptions = [],
  annotations = { },
}: ReportListProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [assignmentFilter, setAssignmentFilter] = useState<ReportFilterType>("all");
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
  const router = useRouter();

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

  const reportsDict = useReportStore((state) => state.reports);
  const setReportFlag = useReportStore((state) => state.setFlag);
  const reportsList = useMemo(() => Object.values(reportsDict), [reportsDict]);

  const filteredReports = filterReports(reportsList, annotations, searchQuery, assignmentFilter);

  useEffect(() => {
    if (!flagDialogOpen || !selectedFlagReport) {
      return;
    }

    let cancelled = false;

    const loadExistingFlag = async () => {
      try {
        const response = await fetch(
          `/api/meerkat/reports/${selectedFlagReport.id}/flag`,
          { cache: "no-store" }
        );

        if (!response.ok) {
          throw new Error("Unable to retrieve report flag.");
        }

        const payload = (await response.json()) as
          | { message?: string; public?: boolean }
          | null;

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
      const response = await fetch(`/api/meerkat/reports/${selectedFlagReport.id}/flag`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: flagDetails.trim(),
          public: flagVisibility === "public",
        }),
      });

      if (!response.ok) {
        throw new Error("Unable to submit report flag.");
      }

      setReportFlag(selectedFlagReport.id, flagDetails.trim());

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
      const response = await fetch(`/api/meerkat/reports/${reportId}/flag`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Unable to delete report flag.");
      }

      setReportFlag(reportId, undefined);
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

    // 2. Pass the sanitized filename to the API
    const response = await fetch(`/api/meerkat/reports/${reportId}/pdf?filename=${encodeURIComponent(`${reportId} - ${safeTitle || "report"}.pdf`)}`, {
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("Failed to download PDF");
    }

    const blob = await response.blob();
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

  return (
    <div className="h-full flex flex-col pt-5">
      <div className="px-4 pb-4 border-b border-border">
        <div className="flex items-center gap-2">
          <FileText className="h-6 w-6 text-primary" />
          <h2 className="text-xl font-semibold">Reports</h2>
          <span className="text-sm text-muted-foreground">
            ({filteredReports.length})
            {searchQuery && ` of ${reportsList.length}`}
          </span>
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

            <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap shrink-0">
              <span className="text-xs text-muted-foreground whitespace-nowrap">
                Filter:
              </span>
              <div className="flex gap-1">
                <Button
                  key="all"
                  variant={assignmentFilter === "all" ? "default" : "outline"}
                  size="sm"
                  className="h-7 text-xs px-3"
                  onClick={() => setAssignmentFilter("all" as ReportFilterType)}
                >
                  {"All"}
                </Button>
                {filterOptions.map((filter) => (
                  <Button
                    key={filter.value}
                    variant={assignmentFilter === filter.value ? "default" : "outline"}
                    size="sm"
                    className="h-7 text-xs px-3"
                    onClick={() => setAssignmentFilter(filter.value as ReportFilterType)}
                  >
                    {filter.label}
                  </Button>
                ))}
              </div>
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
              const displayDate = report.report.year
                ? report.report.year.toString()
                : null;

              const hasAbstract = report.report.abstract && report.report.abstract.length > 0;
              const isSelected = selectedReportId === report.report.reportId;
              const isExpanded = isSelected && hasAbstract;
              const isRunningEvaluation = runningEvaluations.includes(report.report.reportId);
              const reportResults = storeResults[report.report.reportId];
              const resultCount = reportResults ? Object.keys(reportResults).length : 0;
              const flagMessage = report.flag?.trim() ?? "";
              const hasFlag = Boolean(flagMessage);
              const params = new URLSearchParams(
                Object.entries({ ...queryParams })
                  .filter(([_, v]) => v !== undefined)
                  .map(([k, v]) => [k, String(v)])
              ).toString();
              const reportHref = `/${baseUrl}/${projectId}/${report.report.reportId}${params ? `?${params}` : ""}`;
              const pdfParams = new URLSearchParams({
                filename: `${report.report.reportId} - ${report.report.title}.pdf`,
              }).toString();
              const pdfUrl = `/api/meerkat/reports/${report.report.reportId}/pdf?${pdfParams}`;

              if (!reportHref) {
                return null;
              }

              return (
                <div key={report.report.reportId || idx} className="relative">
                  <div
                    ref={isSelected ? selectedCardRef : undefined}
                    tabIndex={0}
                    role="link"
                    aria-selected={isSelected}
                    onClick={() => router.push(reportHref, { scroll: true })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        router.push(reportHref, { scroll: true });
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
                          {report.report.title}
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
                                  aria-label={`More actions for ${report.report.title}`}
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
                                    window.open(pdfUrl, "_blank", "noopener,noreferrer");
                                  }}
                                >
                                  <ExternalLink className="h-4 w-4" />
                                  Open PDF
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  onSelect={() => {
                                    void handleDownloadReportPdf(
                                      report.report.reportId,
                                      report.report.title
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
                                      handleOpenFlagDialog(report.report.reportId, report.report.title);
                                    }}
                                  >
                                    <Flag className="h-4 w-4" />
                                    {hasFlag ? "Edit flag" : "Flag report"}
                                  </DropdownMenuItem>
                                )}
                                {editMode && hasFlag && (
                                  <DropdownMenuItem
                                    disabled={isDeletingFlagReportId === report.report.reportId}
                                    onSelect={() => {
                                      void handleDeleteFlag(report.report.reportId);
                                    }}
                                  >
                                    <FlagOff className="h-4 w-4" />
                                    {isDeletingFlagReportId === report.report.reportId
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
                        {report.report.authors && report.report.authors.length > 0 && (
                          <div className="flex items-center gap-1.5">
                            <Users className="h-3.5 w-3.5 shrink-0" />
                            <span className={isExpanded ? "" : "truncate max-w-[200px]"}>
                              {report.report.authors.join(", ")}
                            </span>
                          </div>
                        )}
                      </div>

                      {hasAbstract && !isExpanded && (
                        <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2 mt-2">
                          {report.report.abstract}
                        </p>
                      )}
                      {editMode && (
                        <ReportAssignedStudiesBadges report={report} />
                      )}
                    </div>

                    {hasAbstract && isExpanded && (
                      <div className="px-4 pb-4 border-t bg-muted/30">
                        <div className="text-xs text-muted-foreground leading-relaxed mt-2 whitespace-pre-wrap">
                          <Abstract text={report.report.abstract}></Abstract>
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
