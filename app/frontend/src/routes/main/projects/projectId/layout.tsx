import { useCallback } from "react";
import { useParams, Outlet } from "react-router-dom";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { getProjectReports } from "@/lib/api/projectApi";
import { useProjectResource } from "@/hooks/use-project-resource";
import { ProjectNotFound } from "@/components/reports/project-not-found";
import { ReportSplitView, ReportSplitViewSkeleton } from "@/components/reports/report-split-view";
import { StudyColumnSkeleton } from "@/components/reports/workbench-skeleton";
import type { GetProjectReportsParams, Page, ReportCurationDto, ReportFilterDimension } from "@/types/apiDTOs";
import StudySheet from "./study-sheet";

const emptyPage: Page<ReportCurationDto> = { items: [], nextCursor: null };

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
  const { data: firstPage, notFound } = useProjectResource(
    () => fetchReports(projectId).then((result) => result ?? emptyPage),
    emptyPage,
    [projectId]
  );

  if (notFound) return <ProjectNotFound />;
  if (firstPage === null) return <ReportSplitViewSkeleton panelSkeleton={<StudyColumnSkeleton />} />;

  return (
    <ReportSplitView
      projectId={projectId}
      firstPage={firstPage}
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
