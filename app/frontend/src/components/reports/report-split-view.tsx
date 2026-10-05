import { useEffect, type ComponentProps, type ReactNode } from "react";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import { DetailsSheetProvider } from "@/context/details-sheet-context";
import { ReportList } from "@/components/ui/report-view/report-list";
import { useReportStore } from "@/hooks/use-report-store";
import type { ReportCurationDto } from "@/types/apiDTOs";

type ReportListProps = ComponentProps<typeof ReportList>;

interface ReportSplitViewProps
  extends Pick<ReportListProps, "baseUrl" | "editMode" | "filterDimensions" | "fetchReports"> {
  projectId: string;
  reports: ReportCurationDto[];
  /** Rendered next to the panels inside a DetailsSheetProvider (e.g. the study sheet). */
  sheet?: ReactNode;
  children: ReactNode;
}

/** Report list on the left, the routed report details on the right. */
export function ReportSplitView({
  projectId,
  reports,
  sheet,
  children,
  ...listProps
}: ReportSplitViewProps) {
  const panelBaseId = `project-panels-${projectId}`;
  const setReports = useReportStore((state) => state.setReports);

  useEffect(() => {
    setReports(reports);
  }, [reports, setReports]);

  const panels = (
    <ResizablePanelGroup id={panelBaseId} direction="horizontal" className="h-full">
      <ResizablePanel
        id={`${panelBaseId}-reports`}
        defaultSize={55}
        minSize={25}
        className="border-r bg-background min-w-0 flex-[0_0_55%]"
      >
        <ReportList {...listProps} initialReports={reports} />
      </ResizablePanel>

      <ResizableHandle
        id={`${panelBaseId}-resize-handle`}
        className="w-1 bg-border hover:bg-primary transition-colors cursor-col-resize"
      />

      <ResizablePanel
        id={`${panelBaseId}-details`}
        defaultSize={45}
        minSize={35}
        className="min-w-0 flex-[0_0_45%]"
      >
        {children}
      </ResizablePanel>
    </ResizablePanelGroup>
  );

  if (!sheet) return panels;

  return (
    <DetailsSheetProvider>
      {panels}
      {sheet}
    </DetailsSheetProvider>
  );
}
