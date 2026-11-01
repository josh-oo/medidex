import { useCallback, useEffect, useState } from "react";
import { useParams, Outlet, useNavigate } from "react-router-dom";
import { refreshStudyDatabases } from "@/lib/databases";
import { curationPaths } from "@/lib/curation-steps";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { AdminGuard } from "@/components/auth/admin-guard";
import type { GetProjectReportsParams, ProjectAnnotationsDto, ReportCurationDto, ReportFilterDimension } from "@/types/apiDTOs";
import { getAnnotations, getProjectReportsReview } from "@/lib/api/projectApi";
import { ReviewAnnotationsProvider } from "./components/review-annotations-context";
import { useAuthStore } from "@/hooks/use-auth";
import { useProjectResource } from "@/hooks/use-project-resource";
import { ProjectNotFound } from "@/components/reports/project-not-found";
import { ReportSplitView, ReportSplitViewSkeleton } from "@/components/reports/report-split-view";
import { Skeleton } from "@/components/ui/skeleton";
import { Widget } from "@/components/ui/widget";
import { CircleCheckBig, Trash2 } from "lucide-react";
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
  // Bumped when a report is merged or deleted: it has left the review, so the list is loaded again, and the numbers of
  // the database change.
  const [version, setVersion] = useState(0);
  const reportFinished = useCallback(() => {
    setVersion((value) => value + 1);
    void refreshStudyDatabases();
  }, []);
  const navigate = useNavigate();
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
    [projectId, version],
    isAdmin
  );

  // The last report is merged or deleted: there is nothing left to review, back to the updates.
  useEffect(() => {
    if (version > 0 && data !== null && data.reports.length === 0) {
      navigate(curationPaths.overview, { replace: true });
    }
  }, [version, data, navigate]);

  return (
    <AdminGuard>
      {notFound ? (
        <ProjectNotFound />
      ) : data === null ? (
        <ReportSplitViewSkeleton panelSkeleton={<ReviewPanelSkeleton />} />
      ) : (
        <div className="h-full flex flex-col overflow-hidden">
          <div className="flex-1 min-h-0 bg-background">
            <ReviewAnnotationsProvider annotations={data.annotations} onReportFinished={reportFinished}>
              <ReportSplitView
                projectId={projectId}
                reports={data.reports}
                baseUrl="curation/review"
                editMode={false}
                filterDimensions={reportFilterDimensions}
                fetchReports={fetchReports}
                sheet={<StudySheet />}
                panelSkeleton={<ReviewPanelSkeleton />}
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

// The review panel (./reportId/page.tsx) while it loads: its widgets with their headers and texts, and study rows as
// outlines of the height of real ones.
function ReviewPanelSkeleton() {
  return (
    <div className="space-y-4 pb-20" aria-busy="true">
      <Widget title="Final selection" icon={CircleCheckBig}>
        <p className="-mt-1 mb-4 text-sm text-muted-foreground">
          Select one or more studies from the annotator suggestions.
        </p>
        <div className="space-y-3">
          {[0, 1].map((index) => (
            <div key={index} className="flex flex-col gap-3 rounded-xl border bg-card p-4">
              <Skeleton className="h-6 w-2/5" />
              <Skeleton className="h-4 w-3/5" />
              <div className="border-t border-border/60 pt-2">
                <Skeleton className="h-4 w-64" />
              </div>
            </div>
          ))}
        </div>
      </Widget>
      <Widget title="Delete report" icon={Trash2}>
        <p className="-mt-1 mb-4 text-sm text-muted-foreground">
          Removes the report from the update; it is kept in the archive only, never added to the database.
        </p>
        <Skeleton className="h-8 w-28 rounded-md" />
      </Widget>
    </div>
  );
}
