import { useCallback, useEffect } from "react";
import { useParams, Outlet } from "react-router-dom";
import { getProjectReportsIntake, streamProjectIntakeUpdates } from "@/lib/api/projectApi";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { useReportStore } from "@/hooks/use-report-store";
import { useProjectResource } from "@/hooks/use-project-resource";
import { ProjectNotFound } from "@/components/reports/project-not-found";
import { ReportSplitView, ReportSplitViewSkeleton } from "@/components/reports/report-split-view";
import { PdfStatusDot } from "@/components/reports/pdf-status";
import { Skeleton } from "@/components/ui/skeleton";
import { Widget } from "@/components/ui/widget";
import { FileText, Link2 } from "lucide-react";
import type { GetProjectReportsParams, Page, ReportFilterDimension, ReportIntakeDto } from "@/types/apiDTOs";

const emptyPage: Page<ReportIntakeDto> = { items: [], nextCursor: null };

const reportFilterDimensions: ReportFilterDimension[] = [
  { field: "withPdf", label: "PDF", onlyLabel: "Has PDF", excludeLabel: "No PDF" },
];

export default function PdfUploadPage() {
  const { projectId } = useParams<{ projectId: string }>() as { projectId: string };
  const { reportIncludes } = useExtensionRegistry();
  const updateReport = useReportStore((state) => state.updateReport);
  const fetchReports = useCallback(
    (id: string, filters?: GetProjectReportsParams) => getProjectReportsIntake(id, { ...filters, include: reportIncludes }),
    [reportIncludes]
  );
  const { data: firstPage, notFound } = useProjectResource(
    () => fetchReports(projectId).then((result) => result ?? emptyPage),
    emptyPage,
    [projectId]
  );

  // A report that changes (its PDF arrives, its postprocessing moves on) comes in again as a whole; started once the list has
  // filled the store (the split view does that), so it is not reset over the newer rows.
  const loaded = firstPage !== null;
  useEffect(() => {
    if (!loaded) return;
    return streamProjectIntakeUpdates(projectId, updateReport, reportIncludes);
  }, [projectId, loaded, updateReport, reportIncludes]);

  return (
    <>
      {notFound ? (
        <ProjectNotFound />
      ) : firstPage === null ? (
        <ReportSplitViewSkeleton panelSkeleton={<PdfPanelSkeleton />} />
      ) : (
        <div className="h-full flex flex-col overflow-hidden">
          <div className="flex-1 min-h-0 bg-background">
            <ReportSplitView
              projectId={projectId}
              firstPage={firstPage}
              baseUrl="curation/pdf-upload"
              editMode={false}
              filterDimensions={reportFilterDimensions}
              fetchReports={fetchReports}
              renderStatus={(report) => <PdfStatusDot projectId={projectId} reportId={report.reportId} />}
              panelSkeleton={<PdfPanelSkeleton />}
            >
              <Outlet />
            </ReportSplitView>
          </div>
        </div>
      )}
    </>
  );
}

// The PDF panel (./reportId/page.tsx) while it loads: its widgets with their headers, and the upload area at its size.
function PdfPanelSkeleton() {
  return (
    <div className="space-y-4 pb-20" aria-busy="true">
      <Widget title="Find the PDF" icon={Link2}>
        <div className="space-y-2.5">
          <Skeleton className="h-3.5 w-1/3" />
          <Skeleton className="h-3.5 w-2/3" />
        </div>
      </Widget>
      <Widget title="PDF" icon={FileText}>
        <Skeleton className="h-32 w-full rounded-lg" />
      </Widget>
    </div>
  );
}
