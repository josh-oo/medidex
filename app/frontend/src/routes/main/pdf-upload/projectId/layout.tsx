import { useParams, Outlet } from "react-router-dom";
import { AdminGuard } from "@/components/auth/admin-guard";
import { getProjectReportsIntake } from "@/lib/api/projectApi";
import { useAuthStore } from "@/hooks/use-auth";
import { useProjectResource } from "@/hooks/use-project-resource";
import { ProjectNotFound } from "@/components/reports/project-not-found";
import { ReportSplitView, ReportSplitViewSkeleton } from "@/components/reports/report-split-view";
import { Skeleton } from "@/components/ui/skeleton";
import { Widget } from "@/components/ui/widget";
import { FileText, Link2, Upload } from "lucide-react";
import type { ReportFilterDimension } from "@/types/apiDTOs";

const reportFilterDimensions: ReportFilterDimension[] = [
  { field: "withPdf", label: "PDF", onlyLabel: "Has PDF", excludeLabel: "No PDF" },
];

export default function PdfUploadPage() {
  const { projectId } = useParams<{ projectId: string }>() as { projectId: string };
  const isAdmin = useAuthStore((s) => s.user?.isAdmin ?? false);
  const { data: reports, notFound } = useProjectResource(
    () => getProjectReportsIntake(projectId).then((result) => result?.items ?? []),
    [],
    [projectId],
    isAdmin
  );

  return (
    <AdminGuard>
      {notFound ? (
        <ProjectNotFound />
      ) : reports === null ? (
        <ReportSplitViewSkeleton panelSkeleton={<PdfPanelSkeleton />} />
      ) : (
        <div className="h-full flex flex-col overflow-hidden">
          <div className="flex-1 min-h-0 bg-background">
            <ReportSplitView
              projectId={projectId}
              reports={reports}
              baseUrl="curation/pdf-upload"
              editMode={false}
              filterDimensions={reportFilterDimensions}
              fetchReports={getProjectReportsIntake}
              panelSkeleton={<PdfPanelSkeleton />}
            >
              <Outlet />
            </ReportSplitView>
          </div>
        </div>
      )}
    </AdminGuard>
  );
}

// The PDF panel (./reportId/page.tsx) while it loads: its widgets with their headers, the upload area and the preview
// at their sizes.
function PdfPanelSkeleton() {
  return (
    <div className="space-y-4 pb-20" aria-busy="true">
      <Widget title="Find the PDF" icon={Link2}>
        <div className="space-y-2.5">
          <Skeleton className="h-3.5 w-1/3" />
          <Skeleton className="h-3.5 w-2/3" />
        </div>
      </Widget>
      <Widget title="Upload PDF" icon={Upload}>
        <Skeleton className="h-32 w-full rounded-lg" />
      </Widget>
      <Widget title="PDF" icon={FileText}>
        <Skeleton className="mx-auto h-[396px] w-[280px] rounded-md" />
      </Widget>
    </div>
  );
}
