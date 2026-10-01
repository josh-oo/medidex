"use client"

import { useEffect, useState } from "react";
import {
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Separator } from "../separator";
import { FileText, Download } from "lucide-react";
import { StudyOverview } from "@/components/ui/study-view/study-details-overview";
import { StudyAspects, type AspectPageState } from "@/components/ui/study-view/study-details-aspects";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { StudyDto, TagDto, Page } from "@/types/apiDTOs";
import {
  getStudyById,
  getReportsByStudyId,
  getInterventionsForStudy,
  getConditionsForStudy,
  getOutcomesForStudy,
  getParticipantsForStudy,
  getDesignForStudy,
} from "@/lib/api/studiesApi";
import { getReportPdf } from "@/lib/api/reportApi";

type ReportListItem = {
  reportId: number;
  title: string;
};

const normalizeReports = (
  items?: Array<{ reportId: number; title?: string | null }>
): ReportListItem[] =>
  (items ?? []).map((report) => ({
    reportId: report.reportId,
    title: report.title ?? `Report ${report.reportId}`,
  }));

const EMPTY_ASPECT_PAGE: AspectPageState = {
  items: [],
  nextCursor: null,
  loadingMore: false,
};

const pageToAspectState = (page: Page<TagDto>): AspectPageState => ({
  items: page.items,
  nextCursor: page.nextCursor,
  loadingMore: false,
});

interface StudyDetailsProps {
  study: StudyDto | null;
  isActive: boolean;
}

export function StudyDetails({ study, isActive }: StudyDetailsProps) {
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [reportsNextCursor, setReportsNextCursor] = useState<string | null>(null);
  const [loadingMoreReports, setLoadingMoreReports] = useState(false);

  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);

  const [interventions, setInterventions] = useState<AspectPageState>(EMPTY_ASPECT_PAGE);
  const [conditions, setConditions] = useState<AspectPageState>(EMPTY_ASPECT_PAGE);
  const [outcomes, setOutcomes] = useState<AspectPageState>(EMPTY_ASPECT_PAGE);
  const [participants, setParticipants] = useState<AspectPageState>(EMPTY_ASPECT_PAGE);
  const [design, setDesign] = useState<AspectPageState>(EMPTY_ASPECT_PAGE);

  const [downloadingPdfs, setDownloadingPdfs] = useState<Set<number>>(new Set());
  const [downloadingSingle, setDownloadingSingle] = useState<Set<number>>(
    new Set()
  );

  useEffect(() => {
    if (!study || !isActive) {
      setReports([]);
      setReportsNextCursor(null);
      setInterventions(EMPTY_ASPECT_PAGE);
      setConditions(EMPTY_ASPECT_PAGE);
      setOutcomes(EMPTY_ASPECT_PAGE);
      setParticipants(EMPTY_ASPECT_PAGE);
      setDesign(EMPTY_ASPECT_PAGE);
      setDetailsLoading(false);
      setDetailsError(null);
      return;
    }

    let requestActive = true;
    const studyId = study.studyId;

    setDetailsLoading(true);
    setDetailsError(null);

    // One call to the combined GET /studies/{study_id} endpoint replaces what used
    // to be six separate requests (reports + the five aspect lists below) - each
    // comes back as just its first page, paged further via its own "Load more".
    const fetchDetails = async () => {
      try {
        const full = await getStudyById(studyId);
        if (!requestActive) return;
        setReports(normalizeReports(full.reports.items));
        setReportsNextCursor(full.reports.nextCursor);
        setInterventions(pageToAspectState(full.interventions));
        setConditions(pageToAspectState(full.conditions));
        setOutcomes(pageToAspectState(full.outcomes));
        setParticipants(pageToAspectState(full.participants));
        setDesign(pageToAspectState(full.design));
      } catch (error) {
        if (!requestActive) return;
        const message =
          error instanceof Error ? error.message : "Unable to load study details";
        setDetailsError(message);
        toast.error(`Failed to load study details: ${message}`);
      } finally {
        if (requestActive) {
          setDetailsLoading(false);
        }
      }
    };

    void fetchDetails();

    return () => {
      requestActive = false;
    };
  }, [study, isActive]);

  if (!study) {
    return null;
  }

  const studyId = study.studyId;
  const studyShortName = study.shortName ?? "study";

  const handleLoadMoreReports = async () => {
    if (!reportsNextCursor) return;

    setLoadingMoreReports(true);
    try {
      const page = await getReportsByStudyId(studyId, undefined, reportsNextCursor);
      setReports((prev) => [...prev, ...normalizeReports(page.items)]);
      setReportsNextCursor(page.nextCursor);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unable to load more reports";
      toast.error(`Failed to load more reports: ${message}`);
    } finally {
      setLoadingMoreReports(false);
    }
  };

  const loadMoreAspect = async (
    state: AspectPageState,
    setState: React.Dispatch<React.SetStateAction<AspectPageState>>,
    fetchPage: (cursor: string) => Promise<Page<TagDto>>,
    label: string
  ) => {
    if (!state.nextCursor || state.loadingMore) return;

    setState((prev) => ({ ...prev, loadingMore: true }));
    try {
      const page = await fetchPage(state.nextCursor);
      setState((prev) => ({
        items: [...prev.items, ...page.items],
        nextCursor: page.nextCursor,
        loadingMore: false,
      }));
    } catch (error) {
      setState((prev) => ({ ...prev, loadingMore: false }));
      const message =
        error instanceof Error ? error.message : `Unable to load more ${label}`;
      toast.error(`Failed to load more ${label}: ${message}`);
    }
  };

  const handleLoadMoreInterventions = () =>
    loadMoreAspect(
      interventions,
      setInterventions,
      (cursor) => getInterventionsForStudy(studyId, undefined, cursor),
      "interventions"
    );
  const handleLoadMoreConditions = () =>
    loadMoreAspect(
      conditions,
      setConditions,
      (cursor) => getConditionsForStudy(studyId, undefined, cursor),
      "conditions"
    );
  const handleLoadMoreOutcomes = () =>
    loadMoreAspect(
      outcomes,
      setOutcomes,
      (cursor) => getOutcomesForStudy(studyId, undefined, cursor),
      "outcomes"
    );
  const handleLoadMoreParticipants = () =>
    loadMoreAspect(
      participants,
      setParticipants,
      (cursor) => getParticipantsForStudy(studyId, undefined, cursor),
      "participants"
    );
  const handleLoadMoreDesign = () =>
    loadMoreAspect(
      design,
      setDesign,
      (cursor) => getDesignForStudy(studyId, undefined, cursor),
      "design"
    );

  const handleDownloadAllReportPdfs = async () => {
    if (reports.length === 0) return;

    setDownloadingPdfs(new Set([studyId]));
    let successCount = 0;
    let failureCount = 0;

    try {
      for (const report of reports) {
        try {
          const buffer = await getReportPdf(report.reportId);
          const blob = new Blob([buffer], { type: "application/pdf" });
          const url = URL.createObjectURL(blob);
          const link = document.createElement("a");
          link.href = url;
          link.download = `${studyShortName}_Report_${report.reportId}.pdf`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
          successCount++;
        } catch (error) {
          failureCount++;
          toast.error(
            `Failed to download report ${report.reportId}: ${
              error instanceof Error ? error.message : "Unknown error"
            }`
          );
        }
        await new Promise((resolve) => setTimeout(resolve, 300));
      }

      if (successCount > 0) {
        toast.success(
          `Downloaded ${successCount} PDF${
            successCount > 1 ? "s" : ""
          }${failureCount > 0 ? ` (${failureCount} failed)` : ""}`
        );
      }
    } finally {
      setDownloadingPdfs(new Set());
    }
  };

  const handleDownloadSingleReportPdf = async (reportId: number) => {
    setDownloadingSingle((prev) => {
      const newSet = new Set(prev);
      newSet.add(reportId);
      return newSet;
    });

    try {
      const buffer = await getReportPdf(reportId);
      const blob = new Blob([buffer], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${studyShortName}_Report_${reportId}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success(`Downloaded report ${reportId}`);
    } catch (error) {
      toast.error(
        `Failed to download report ${reportId}: ${
          error instanceof Error ? error.message : "Unknown error"
        }`
      );
    } finally {
      setDownloadingSingle((prev) => {
        const newSet = new Set(prev);
        newSet.delete(reportId);
        return newSet;
      });
    }
  };

  return (
    <SheetContent
      side="right"
      className="w-full sm:max-w-2xl overflow-y-auto pb-8"
    >
      <>
        <SheetHeader className="border-b border-border/60">
          <SheetTitle className="text-lg">{studyShortName}</SheetTitle>
          {study.trialId !== null && (
            <SheetDescription className="font-mono text-xs">
              {study.trialId}
            </SheetDescription>
          )}
        </SheetHeader>
        <div className="space-y-6">
          <StudyOverview study={study} />

          <Separator />

          <StudyAspects
            study={study}
            loading={detailsLoading}
            error={detailsError}
            interventions={interventions}
            conditions={conditions}
            outcomes={outcomes}
            participants={participants}
            design={design}
            onLoadMoreInterventions={handleLoadMoreInterventions}
            onLoadMoreConditions={handleLoadMoreConditions}
            onLoadMoreOutcomes={handleLoadMoreOutcomes}
            onLoadMoreParticipants={handleLoadMoreParticipants}
            onLoadMoreDesign={handleLoadMoreDesign}
          />

          <Separator />

          <div className="space-y-4 px-4">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold flex items-center gap-2.5">
                <div className="p-1.5 rounded-md bg-muted">
                  <FileText className="h-4 w-4" />
                </div>
                Reports
                <Badge variant="secondary" className="text-xs font-normal">
                  {reportsNextCursor ? `${reports.length}+` : reports.length}
                </Badge>
              </h3>
              {reports.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDownloadAllReportPdfs}
                  disabled={
                    detailsLoading ||
                    downloadingPdfs.has(studyId)
                  }
                  className="flex items-center gap-2"
                >
                  <Download className="h-4 w-4" />
                  {downloadingPdfs.has(studyId)
                    ? "Downloading..."
                    : "Download All PDFs"}
                </Button>
              )}
            </div>

            <div className="space-y-2">
              {detailsLoading && (
                <div className="px-4">
                  <div className="space-y-2 rounded-md border border-border/60 bg-muted/30 p-3.5">
                    <div className="flex items-center gap-3">
                      <Skeleton className="h-6 w-6 rounded-md" />
                      <Skeleton className="h-4 w-40" />
                      <Skeleton className="h-3 w-16" />
                    </div>
                    <Skeleton className="h-3 w-full" />
                  </div>
                </div>
              )}
              {detailsError && (
                <p className="px-4 text-sm text-destructive">{detailsError}</p>
              )}
              {reports.length > 0 ? (
                reports.map((report) => (
                  <div
                    key={report.reportId}
                    className="p-3.5 rounded-md border border-border/60 bg-muted/30 hover:bg-muted/50 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium leading-snug">
                          {report.title}
                        </p>
                        <div className="flex items-center gap-3 mt-2">
                          <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">
                            Report ID: {report.reportId}
                          </code>
                        </div>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          handleDownloadSingleReportPdf(report.reportId)
                        }
                        disabled={downloadingSingle.has(report.reportId)}
                        className="h-8 w-8 p-0 flex items-center justify-center shrink-0"
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))
              ) : (
                !detailsLoading &&
                !detailsError && (
                  <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                    <FileText className="h-8 w-8 mb-2 opacity-30" />
                    <p className="text-sm">No reports available</p>
                  </div>
                )
              )}
              {reportsNextCursor && !detailsLoading && (
                <div className="flex justify-center pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleLoadMoreReports}
                    disabled={loadingMoreReports}
                  >
                    {loadingMoreReports ? "Loading..." : "Load more"}
                  </Button>
                </div>
              )}
            </div>
          </div>
        </div>
      </>
    </SheetContent>
  );
}
