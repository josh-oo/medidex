"use client"

import { useEffect, useState } from "react";
import {
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Separator } from "../separator";
import { FileText, Download } from "lucide-react";
import { StudyOverview } from "@/components/ui/study-view/study-details-overview";
import { StudyAspects } from "@/components/ui/study-view/study-details-aspects";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { StudyDto } from "@/types/apiDTOs";

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

interface StudyDetailsProps {
  study: StudyDto | null;
  isActive: boolean;
}

export function StudyDetails({ study, isActive }: StudyDetailsProps) {
  const [reports, setReports] = useState<ReportListItem[]>([]);
  const [reportsLoading, setReportsLoading] = useState(false);
  const [reportsError, setReportsError] = useState<string | null>(null);
  const [downloadingPdfs, setDownloadingPdfs] = useState<Set<number>>(new Set());
  const [downloadingSingle, setDownloadingSingle] = useState<Set<number>>(
    new Set()
  );

  useEffect(() => {
    if (!study || !isActive) {
      setReports([]);
      setReportsLoading(false);
      setReportsError(null);
      return;
    }

    let requestActive = true;
    const studyId = study.studyId;

    setReportsLoading(true);
    setReportsError(null);

    const fetchReports = async () => {
      try {
        const response = await fetch(
          `/api/meerkat/studies/${studyId}/reports`,
          { cache: "no-store" }
        );

        if (!response.ok) {
          throw new Error("Failed to load reports");
        }

        const data: ReportListItem[] = await response.json();
        if (!requestActive) return;
        setReports(normalizeReports(data));
      } catch (error) {
        if (!requestActive) return;
        const message =
          error instanceof Error ? error.message : "Unable to load reports";
        setReportsError(message);
        toast.error(`Failed to load reports: ${message}`);
      } finally {
        if (!requestActive) return;
        setReportsLoading(false);
      }
    };

    void fetchReports();

    return () => {
      requestActive = false;
    };
  }, [study, isActive]);

  if (!study) {
    return null;
  }

  const studyId = study.studyId;
  const studyShortName = study.shortName ?? "study";

  const handleDownloadAllReportPdfs = async () => {
    if (reports.length === 0) return;

    setDownloadingPdfs(new Set([studyId]));
    let successCount = 0;
    let failureCount = 0;

    try {
      for (const report of reports) {
        try {
          const response = await fetch(
            `/api/meerkat/reports/${report.reportId}/pdf`,
            { cache: "no-store" }
          );
          if (!response.ok) {
            throw new Error("Failed to download PDF");
          }
          const blob = await response.blob();
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
      const response = await fetch(
        `/api/meerkat/reports/${reportId}/pdf`,
        { cache: "no-store" }
      );
      if (!response.ok) {
        throw new Error("Failed to download PDF");
      }
      const blob = await response.blob();
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
        </SheetHeader>
        <div className="space-y-6">
          <StudyOverview study={study} />

          <Separator />

          <StudyAspects study={study}
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
                  {reports.length}
                </Badge>
              </h3>
              {reports.length > 0 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleDownloadAllReportPdfs}
                  disabled={
                    reportsLoading ||
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
              {reportsLoading && (
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
              {reportsError && (
                <p className="px-4 text-sm text-destructive">{reportsError}</p>
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
                !reportsLoading &&
                !reportsError && (
                  <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                    <FileText className="h-8 w-8 mb-2 opacity-30" />
                    <p className="text-sm">No reports available</p>
                  </div>
                )
              )}
            </div>
          </div>
        </div>
      </>
    </SheetContent>
  );
}
