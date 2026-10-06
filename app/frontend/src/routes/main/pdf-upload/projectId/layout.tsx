import { useParams, Outlet } from "react-router-dom";
import { AdminGuard } from "@/components/auth/admin-guard";
import { getProjectReportsIntake } from "@/lib/api/projectApi";
import { Spinner } from "@/components/ui/spinner";
import { useAuthStore } from "@/hooks/use-auth";
import { useProjectResource } from "@/hooks/use-project-resource";
import { ProjectNotFound } from "@/components/reports/project-not-found";
import { ReportSplitView } from "@/components/reports/report-split-view";
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
        <div className="flex h-full w-full items-center justify-center">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <div className="h-full flex flex-col overflow-hidden">
          <div className="flex-1 min-h-0 bg-background">
            <ReportSplitView
              projectId={projectId}
              reports={reports}
              baseUrl="pdf-upload"
              editMode={false}
              filterDimensions={reportFilterDimensions}
              fetchReports={getProjectReportsIntake}
            >
              <Outlet />
            </ReportSplitView>
          </div>
        </div>
      )}
    </AdminGuard>
  );
}
