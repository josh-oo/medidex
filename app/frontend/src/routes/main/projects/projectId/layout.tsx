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
    const rowPlaceholders = Array.from({ length: 7 });

    return (
        <div className="h-full w-full flex min-w-0 bg-background">
            <div className="min-w-0 flex-[0_0_55%] border-r">
                <div className="h-full flex flex-col pt-5">
                    <div className="px-4 pb-4 border-b border-border space-y-4">
                        <div className="flex items-center gap-2">
                            <Skeleton className="h-6 w-6 rounded" />
                            <Skeleton className="h-7 w-24" />
                            <Skeleton className="h-5 w-10" />
                        </div>

                        <div className="space-y-3">
                            <Skeleton className="h-9 w-full rounded-md" />
                            <div className="flex flex-wrap gap-2 sm:flex-nowrap sm:items-center sm:gap-4">
                                <Skeleton className="h-4 w-10" />
                                <div className="flex gap-1">
                                    <Skeleton className="h-7 w-12 rounded-md" />
                                    <Skeleton className="h-7 w-16 rounded-md" />
                                    <Skeleton className="h-7 w-20 rounded-md" />
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 min-h-0 overflow-hidden px-4">
                        <div className="space-y-3 pb-4 pt-3">
                            {rowPlaceholders.map((_, index) => (
                                <div
                                    key={index}
                                    className="rounded-lg border border-border bg-card p-4"
                                >
                                    <div className="space-y-3">
                                        <div className="flex items-start justify-between gap-3">
                                            <Skeleton className="h-5 w-4/5" />
                                            <Skeleton className="h-8 w-8 rounded-md" />
                                        </div>

                                        <div className="flex items-center gap-3 flex-wrap">
                                            <div className="flex items-center gap-1.5">
                                                <Skeleton className="h-3.5 w-3.5 rounded" />
                                                <Skeleton className="h-4 w-12" />
                                            </div>
                                            <div className="flex items-center gap-1.5">
                                                <Skeleton className="h-3.5 w-3.5 rounded" />
                                                <Skeleton className="h-4 w-36" />
                                            </div>
                                        </div>

                                        <Skeleton className="h-4 w-full" />
                                        <Skeleton className="h-4 w-5/6" />

                                        <div className="flex flex-wrap gap-2 pt-1">
                                            <Skeleton className="h-5 w-20 rounded-full" />
                                            <Skeleton className="h-5 w-24 rounded-full" />
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            <div className="min-w-0 flex-[0_0_45%]">
                <ReportDetailsPanelSkeleton />
            </div>
        </div>
    );
}

function ReportDetailsPanelSkeleton() {
    return (
        <div className="h-full flex flex-col min-w-0 overflow-hidden p-4 md:px-8">
            <div className="space-y-2">
                <Skeleton className="h-6 w-36" />
                <Skeleton className="h-4 w-52" />
            </div>
            <div className="flex-1 mt-4 space-y-4 overflow-hidden">
                <Skeleton className="h-24 w-full rounded-xl" />
                <Skeleton className="h-24 w-full rounded-xl" />
                <Skeleton className="h-24 w-full rounded-xl" />
            </div>
        </div>
    );
}
