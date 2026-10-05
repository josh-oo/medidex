import { useEffect, type ReactNode } from "react";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { DetailsSheetProvider } from "@/context/details-sheet-context";
import { ReportCurationDto, ReportFilterDimension } from "@/types/apiDTOs";
import { ReportList } from "@/components/ui/report-view/report-list";
import { useReportStore } from "@/hooks/use-report-store";
import { getProjectReportsReview } from "@/lib/api/projectApi";
import StudySheet from "../../../projects/projectId/study-sheet";

interface ReportColumnClientProps {
  children: ReactNode;
  reports: ReportCurationDto[];
  projectId: string;
}

const reportFilterDimensions: ReportFilterDimension[] = [
  { field: "consensus", label: "Agreement", onlyLabel: "Consensus", excludeLabel: "Conflict" },
  { field: "reviewed", label: "Review", onlyLabel: "Reviewed", excludeLabel: "Pending review" },
];

export function ReportColumnClient({ children, reports, projectId}: ReportColumnClientProps) {
  const panelBaseId = `project-panels-${projectId}`;
  const reportsPanelId = `${panelBaseId}-reports`;
  const detailsPanelId = `${panelBaseId}-details`;
  const resizeHandleId = `${panelBaseId}-resize-handle`;

  const setReports = useReportStore((state) => state.setReports);
    
  useEffect(() => {
    setReports(reports);
  }, [reports, setReports]);
  
  return (
      <DetailsSheetProvider>
        <ResizablePanelGroup
          id={panelBaseId}
          direction="horizontal"
          className="h-full"
        >
          <ResizablePanel
            id={reportsPanelId}
            defaultSize={55}
            minSize={25}
            className="border-r bg-background min-w-0 flex-[0_0_55%]"
          >
            <ReportList
              baseUrl="review"
              editMode={false}
              filterDimensions={reportFilterDimensions}
              fetchReports={getProjectReportsReview}
              initialReports={reports}
            />
          </ResizablePanel>

          <ResizableHandle
            id={resizeHandleId}
            className="w-1 bg-border hover:bg-primary transition-colors cursor-col-resize"
          />

          <ResizablePanel
            id={detailsPanelId}
            defaultSize={45}
            minSize={35}
            className="min-w-0 flex-[0_0_45%]"
          >
            {children}
          </ResizablePanel>
        </ResizablePanelGroup>
        <StudySheet />
      </DetailsSheetProvider>
  );
}
