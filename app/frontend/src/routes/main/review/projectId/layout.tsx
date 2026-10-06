import { useCallback } from "react";
import { useParams, Outlet } from "react-router-dom";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { AdminGuard } from "@/components/auth/admin-guard";
import type { GetProjectReportsParams, ProjectAnnotationsDto, ReportCurationDto, ReportFilterDimension } from "@/types/apiDTOs";
import { getAnnotations, getProjectReportsReview } from "@/lib/api/projectApi";
import { ReviewAnnotationsProvider } from "./components/review-annotations-context";
import { Spinner } from "@/components/ui/spinner";
import { useAuthStore } from "@/hooks/use-auth";
import { useProjectResource } from "@/hooks/use-project-resource";
import { ProjectNotFound } from "@/components/reports/project-not-found";
import { ReportSplitView } from "@/components/reports/report-split-view";
import StudySheet from "../../projects/projectId/study-sheet";

interface ProjectReviewData {
  reports: ReportCurationDto[];
  annotations: ProjectAnnotationsDto;
}

const reportFilterDimensions: ReportFilterDimension[] = [
  { field: "consensus", label: "Agreement", onlyLabel: "Consensus", excludeLabel: "Conflict" },
  { field: "reviewed", label: "Review", onlyLabel: "Reviewed", excludeLabel: "Pending review" },
];

const emptyReviewData: ProjectReviewData = { reports: [], annotations: {} };

export default function AnnotationsReviewPage() {
  const { projectId } = useParams<{ projectId: string }>() as { projectId: string };
  const isAdmin = useAuthStore((s) => s.user?.isAdmin ?? false);
  const { reportIncludes } = useExtensionRegistry();
  const fetchReports = useCallback(
    (id: string, filters?: GetProjectReportsParams) =>
      getProjectReportsReview(id, { ...filters, include: reportIncludes }),
    [reportIncludes]
  );
  const { data, notFound } = useProjectResource<ProjectReviewData>(
    async () => {
      const [reportsPage, annotations] = await Promise.all([
        fetchReports(projectId),
        getAnnotations(projectId),
      ]);
      return { reports: reportsPage?.items ?? [], annotations: annotations ?? {} };
    },
    emptyReviewData,
    [projectId],
    isAdmin
  );

  return (
    <AdminGuard>
      {notFound ? (
        <ProjectNotFound />
      ) : data === null ? (
        <div className="flex h-full w-full items-center justify-center">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <div className="h-full flex flex-col overflow-hidden">
          <div className="flex-1 min-h-0 bg-background">
            <ReviewAnnotationsProvider annotations={data.annotations}>
              <ReportSplitView
                projectId={projectId}
                reports={data.reports}
                baseUrl="review"
                editMode={false}
                filterDimensions={reportFilterDimensions}
                fetchReports={fetchReports}
                sheet={<StudySheet />}
              >
                <Outlet />
              </ReportSplitView>
            </ReviewAnnotationsProvider>
          </div>
        </div>
      )}
    </AdminGuard>
  );
}
