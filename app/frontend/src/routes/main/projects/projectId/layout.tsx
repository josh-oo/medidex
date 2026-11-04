import { useCallback } from "react";
import { useParams, Outlet } from "react-router-dom";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { getProjectReports } from "@/lib/api/projectApi";
import { useProjectResource } from "@/hooks/use-project-resource";
import { ProjectNotFound } from "@/components/reports/project-not-found";
import { ReportSplitView, ReportSplitViewSkeleton } from "@/components/reports/report-split-view";
import { StudyColumnSkeleton } from "@/components/reports/workbench-skeleton";
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
  if (reports === null) return <ReportSplitViewSkeleton panelSkeleton={<StudyColumnSkeleton />} />;

  return (
    <ReportSplitView
      projectId={projectId}
      reports={reports}
      baseUrl="curation/projects"
      editMode={true}
      filterDimensions={reportFilterDimensions}
      fetchReports={fetchReports}
      sheet={<StudySheet />}
      panelSkeleton={<StudyColumnSkeleton />}
    >
      <Outlet />
    </ReportSplitView>
  );
}
