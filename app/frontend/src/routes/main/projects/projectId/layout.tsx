import { useCallback } from "react";
import { useParams, Outlet } from "react-router-dom";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { getProjectReports } from "@/lib/api/projectApi";
import { Skeleton } from "@/components/ui/skeleton";
import { useProjectResource } from "@/hooks/use-project-resource";
import { ProjectNotFound } from "@/components/reports/project-not-found";
import { ReportSplitView } from "@/components/reports/report-split-view";
import type { GetProjectReportsParams, ReportFilterDimension } from "@/types/apiDTOs";
import StudySheet from "./study-sheet";

const reportFilterDimensions: ReportFilterDimension[] = [
  { field: "processed", label: "Status", onlyLabel: "Processed", excludeLabel: "Unprocessed" },
  { field: "newStudy", label: "Type", onlyLabel: "New study", excludeLabel: "Existing study" },
  { field: "flagged", label: "Flag", onlyLabel: "Flagged", excludeLabel: "Unflagged" },
];

export default function ReportColumn() {
  const { projectId } = useParams<{ projectId: string }>() as { projectId: string };
  const { reportIncludes } = useExtensionRegistry();
  const fetchReports = useCallback(
    (id: string, filters?: GetProjectReportsParams) => getProjectReports(id, { ...filters, include: reportIncludes }),
    [reportIncludes]
  );
  const { data: reports, notFound } = useProjectResource(
    () => fetchReports(projectId).then((result) => result?.items ?? []),
    [],
    [projectId]
  );

  if (notFound) return <ProjectNotFound />;
  if (reports === null) return <ReportColumnSkeleton />;

  return (
    <ReportSplitView
      projectId={projectId}
      reports={reports}
      baseUrl="projects"
      editMode={true}
      filterDimensions={reportFilterDimensions}
      fetchReports={fetchReports}
      sheet={<StudySheet />}
    >
      <Outlet />
    </ReportSplitView>
  );
}

function ReportColumnSkeleton() {
    const rowPlaceholders = Array.from({ length: 10 });

    return (
        <div className="h-full w-full flex min-w-0 bg-canvas">
            <div className="hidden md:flex w-72 lg:w-80 shrink-0 flex-col gap-3 px-3 pt-4">
                <Skeleton className="h-6 w-28" />
                <Skeleton className="h-9 w-full rounded-md" />
                <div className="flex gap-1">
                    <Skeleton className="h-7 w-14 rounded-full" />
                    <Skeleton className="h-7 w-14 rounded-full" />
                    <Skeleton className="h-7 w-14 rounded-full" />
                </div>
                <div className="space-y-2 pt-1">
                    {rowPlaceholders.map((_, index) => (
                        <Skeleton key={index} className="h-9 w-full rounded-xl" />
                    ))}
                </div>
            </div>

            <div className="min-w-0 flex-1 px-3 sm:px-5 pt-14 space-y-4">
                <Skeleton className="h-40 w-full rounded-2xl" />
                <Skeleton className="h-28 w-full rounded-2xl" />
                <Skeleton className="h-64 w-full rounded-2xl" />
            </div>
        </div>
    );
}
