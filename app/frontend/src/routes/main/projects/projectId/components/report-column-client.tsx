"use client";

import { useEffect, type ReactNode } from "react";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { DetailsSheetProvider } from "@/context/details-sheet-context";
import StudySheet from "../study-sheet";
import { ReportDetailDto, ReportFilterDimension } from "@/types/apiDTOs";
import { ReportList } from "@/components/ui/report-view/report-list";
import { useReportStore } from "@/hooks/use-report-store";
import { getProjectReports } from "@/lib/api/projectApi";

const reportFilterDimensions: ReportFilterDimension[] = [
  { field: "processed", label: "Status", onlyLabel: "Processed", excludeLabel: "Unprocessed" },
  { field: "newStudy", label: "Type", onlyLabel: "New study", excludeLabel: "Existing study" },
  { field: "flagged", label: "Flag", onlyLabel: "Flagged", excludeLabel: "Unflagged" },
];

interface ReportColumnClientProps {
  children: ReactNode;
  reports: ReportDetailDto[];
  projectId: string;
}

export function ReportColumnClient({ children, reports, projectId }: ReportColumnClientProps) {
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
            baseUrl="projects"
            editMode={true}
            filterDimensions={reportFilterDimensions}
            fetchReports={getProjectReports}
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
