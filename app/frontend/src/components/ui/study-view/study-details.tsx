import { useEffect, useState } from "react";
import {
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { FileText, Download } from "lucide-react";
import { StudyOverview } from "@/components/ui/study-view/study-details-overview";
import { StudyAspects, type AspectPageState } from "@/components/ui/study-view/study-details-aspects";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { StudyDto, TagDto, Page } from "@/types/apiDTOs";
import { getStudyById, getReportsByStudyId, getTagsForStudy } from "@/lib/api/studiesApi";
import { useStudySchema } from "@/hooks/use-study-schema";
import { getReportPdf } from "@/lib/api/reportApi";
import { Pager } from "@/components/ui/pager";
import { Spinner } from "@/components/ui/spinner";
import { useClientPages } from "@/hooks/use-client-pages";

// Reports of the study shown per page.
const REPORTS_PAGE_SIZE = 5;

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
  /** `inline` renders the details without the sheet around them (e.g. folded out below a study card). */
  variant?: "sheet" | "inline";
}

export function StudyDetails({ study, isActive, variant = "sheet" }: StudyDetailsProps) {
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [reportsNextCursor, setReportsNextCursor] = useState<string | null>(null);
  const [loadingMoreReports, setLoadingMoreReports] = useState(false);

  const [detailsLoading, setDetailsLoading] = useState(false);
  const [detailsError, setDetailsError] = useState<string | null>(null);

  const { schema, error: schemaError } = useStudySchema();
  // The tags of the study per category of the study schema.
  const [tags, setTags] = useState<Record<string, AspectPageState>>({});

  const [downloadingPdfs, setDownloadingPdfs] = useState<Set<number>>(new Set());
  const [downloadingSingle, setDownloadingSingle] = useState<Set<number>>(
    new Set()
  );

  useEffect(() => {
    if (!study || !isActive) {
      setReports([]);
      setReportsNextCursor(null);
      setTags({});
      setDetailsLoading(false);
      setDetailsError(null);
      return;
    }

    let requestActive = true;
    const studyId = study.studyId;

    setDetailsLoading(true);
    setDetailsError(null);

    // One call to the combined GET /studies/{study_id} endpoint replaces what would
    // otherwise be a request per list (reports + the tags of each category) - each
    // comes back as just its first page, paged further via its own "Load more".
    const fetchDetails = async () => {
      try {
        const full = await getStudyById(studyId);
        if (!requestActive) return;
        setReports(normalizeReports(full.reports.items));
        setReportsNextCursor(full.reports.nextCursor);
        setTags(
          Object.fromEntries(
            Object.entries(full.tags).map(([category, page]) => [category, pageToAspectState(page)])
          )
        );
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

  const reportPages = useClientPages({
    items: reports,
    pageSize: REPORTS_PAGE_SIZE,
    hasMore: reportsNextCursor !== null,
    loadMore: () => void handleLoadMoreReports(),
    resetKey: study?.studyId,
  });

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

  const handleLoadMoreTags = async (category: string) => {
    const state = tags[category];
    if (!state?.nextCursor || state.loadingMore) return;

    const update = (change: (previous: AspectPageState) => AspectPageState) =>
      setTags((prev) => ({ ...prev, [category]: change(prev[category] ?? EMPTY_ASPECT_PAGE) }));

    update((prev) => ({ ...prev, loadingMore: true }));
    try {
      const page = await getTagsForStudy(studyId, category, undefined, state.nextCursor);
      update((prev) => ({
        items: [...prev.items, ...page.items],
        nextCursor: page.nextCursor,
        loadingMore: false,
      }));
    } catch (error) {
      update((prev) => ({ ...prev, loadingMore: false }));
      const message =
        error instanceof Error ? error.message : `Unable to load more ${category}`;
      toast.error(`Failed to load more ${category}: ${message}`);
    }
  };

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

  const body = (
        <div className="space-y-3">
          <dl className="divide-y divide-border/50">
            <StudyOverview study={study} fields={schema?.fields ?? []} />
            <StudyAspects
              study={study}
              loading={detailsLoading || !schema}
              error={detailsError ?? schemaError}
              categories={schema?.tags ?? []}
              tags={Object.fromEntries(
                (schema?.tags ?? []).map((category) => [category.key, tags[category.key] ?? EMPTY_ASPECT_PAGE])
              )}
              onLoadMore={handleLoadMoreTags}
            />
          </dl>

          <section>
            <div className="flex items-center gap-2 px-4 pb-1">
              <h4 className="text-xs font-medium text-muted-foreground">
                Reports{" "}
                <span className="tabular-nums">· {reportsNextCursor ? `${reports.length}+` : reports.length}</span>
              </h4>
              <Pager
                className="ml-auto"
                range={reportPages.range}
                canPrev={reportPages.canPrev}
                canNext={reportPages.canNext}
                onPrev={reportPages.prev}
                onNext={reportPages.next}
                loading={loadingMoreReports}
              />
              {reports.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleDownloadAllReportPdfs}
                  disabled={detailsLoading || downloadingPdfs.has(studyId)}
                  className={`h-7 text-xs text-muted-foreground ${reportPages.canPrev || reportPages.canNext ? "" : "ml-auto"}`}
                >
                  <Download className="h-3.5 w-3.5" />
                  {downloadingPdfs.has(studyId) ? "Downloading..." : "Download all"}
                </Button>
              )}
            </div>

            {detailsLoading && (
              <div className="space-y-1.5 px-4">
                <Skeleton className="h-4 w-4/5" />
                <Skeleton className="h-4 w-3/5" />
              </div>
            )}
            {detailsError && (
              <p className="px-4 text-sm text-destructive">{detailsError}</p>
            )}
            {reportPages.isTurning ? (
              <div className="flex justify-center py-4"><Spinner className="h-4 w-4 text-muted-foreground" /></div>
            ) : reports.length > 0 ? (
              <ul className="px-2">
                {reportPages.pageItems.map((report) => (
                  <li
                    key={report.reportId}
                    className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-muted/60"
                  >
                    <span className="shrink-0 font-mono text-xs text-muted-foreground">#{report.reportId}</span>
                    <span className="min-w-0 flex-1 truncate text-sm" title={report.title}>
                      {report.title}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => handleDownloadSingleReportPdf(report.reportId)}
                      disabled={downloadingSingle.has(report.reportId)}
                      className="h-7 w-7 shrink-0 text-muted-foreground"
                      aria-label={`Download the PDF of report ${report.reportId}`}
                    >
                      <Download className="h-3.5 w-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              !detailsLoading &&
              !detailsError && (
                <p className="flex items-center gap-1.5 px-4 text-xs text-muted-foreground">
                  <FileText className="h-3.5 w-3.5 opacity-50" />
                  No reports available
                </p>
              )
            )}
          </section>

          {schema && schema.meta.length > 0 && (
            <div className="flex flex-wrap gap-x-4 gap-y-1 px-4 text-[11px] text-muted-foreground">
              {schema.meta.map((meta) => {
                const value = study[meta.key];
                if (!value) return null;
                return (
                  <span key={meta.key}>
                    {meta.label} {new Date(String(value)).toLocaleDateString()}
                  </span>
                );
              })}
            </div>
          )}
        </div>
  );

  if (variant === "inline") {
    return (
      <div className="py-3">
        {study.trialId !== null && (
          <p className="px-4 pb-2 font-mono text-xs text-muted-foreground">{study.trialId}</p>
        )}
        {body}
      </div>
    );
  }

  return (
    <SheetContent
      side="right"
      className="w-full sm:max-w-2xl overflow-y-auto pb-8"
    >
      <SheetHeader className="border-b border-border/60">
        <SheetTitle className="text-lg">{studyShortName}</SheetTitle>
        {study.trialId !== null && (
          <SheetDescription className="font-mono text-xs">
            {study.trialId}
          </SheetDescription>
        )}
      </SheetHeader>
      {body}
    </SheetContent>
  );
}
