import { useEffect, useRef, useState, type ComponentType } from "react";
import { Download, FileX, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useExtensionRegistry, type ReportPdfSlotProps } from "@/context/extension-registry-context";
import { REPORT_PDF_PANE_WIDTH, useReportPdfPane, type ComparedStudy, type PdfFocus } from "@/context/report-pdf-pane-context";
import { useReportStore } from "@/hooks/use-report-store";
import { getReportPdf } from "@/lib/api/reportApi";
import { getReportsByStudyId } from "@/lib/api/studiesApi";
import { downloadReportPdf } from "@/lib/report-pdf";
import { cn } from "@/lib/utils";
import type { ReportPreviewDto } from "@/types/apiDTOs";
import { ReportPdfComparePicker } from "./report-pdf-compare-picker";

// Where the panel group remembers how high the open report's PDF and the compared one were last.
const COMPARE_SPLIT_STORAGE_KEY = "medidex.report-pdf-compare-split";
// More reports than a study has in practice; the tabs do not page through them.
const STUDY_REPORTS_LIMIT = 50;

interface ReportPdfPaneProps {
  reportId: number;
  focus: PdfFocus | null;
  /** Next to the workbench (rather than over it, on phones): its width is published for dialogs to keep clear of it. */
  docked: boolean;
  onClose: () => void;
}

/** The PDF of the open report next to the workbench: the extension's viewer if there is one, else the browser's. */
export function ReportPdfPane({ reportId, focus, docked, onClose }: ReportPdfPaneProps) {
  const report = useReportStore((state) => state.reports[reportId]);
  const { reportPdf: Viewer = BrowserPdfViewer } = useExtensionRegistry();
  const title = report?.title ?? null;
  const ref = useRef<HTMLElement>(null);
  // The study whose reports' PDFs are shown under the open report's (see ReportPdfPaneState.compared).
  const pane = useReportPdfPane();
  const compared = pane?.compared ?? null;

  useEffect(() => {
    const element = ref.current;
    if (!docked || !element) return;
    const root = document.documentElement;
    const observer = new ResizeObserver(([entry]) =>
      root.style.setProperty(REPORT_PDF_PANE_WIDTH, `${Math.round(entry.borderBoxSize[0]?.inlineSize ?? 0)}px`)
    );
    observer.observe(element);
    return () => {
      observer.disconnect();
      root.style.removeProperty(REPORT_PDF_PANE_WIDTH);
    };
  }, [docked]);

  return (
    <section ref={ref} aria-label="PDF" data-report-pdf-pane="" className="flex h-full min-h-0 flex-col bg-card">
      <header className="flex h-12 shrink-0 items-center gap-1 border-b px-3">
        <h2 className="min-w-0 flex-1 truncate text-sm font-medium" title={title ?? undefined}>
          {title ?? `Report #${reportId}`}
        </h2>
        {pane && <ReportPdfComparePicker reportId={reportId} onPick={pane.compare} />}
        {report?.hasPdf && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Download PDF"
                onClick={() => void downloadReportPdf(reportId, title ?? "")}
              >
                <Download />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Download PDF</TooltipContent>
          </Tooltip>
        )}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button type="button" variant="ghost" size="icon-sm" aria-label="Close PDF" onClick={onClose}>
              <X />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Close PDF</TooltipContent>
        </Tooltip>
      </header>
      {/* Always a panel group, so that comparing does not remount the open report's PDF (and lose its place). */}
      <ResizablePanelGroup direction="vertical" autoSaveId={COMPARE_SPLIT_STORAGE_KEY} className="min-h-0 flex-1">
        <ResizablePanel id="report" order={1} minSize={20}>
          {!report ? null : report.hasPdf ? (
            // Remounted per report, so nothing of the previous report's PDF is shown for the next one.
            <Viewer key={reportId} reportId={reportId} extensions={report.extensions} title={title} focus={focus} />
          ) : (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-sm text-muted-foreground">
              <FileX className="h-5 w-5" />
              This report has no PDF.
            </div>
          )}
        </ResizablePanel>
        {compared && (
          <>
            <ResizableHandle withHandle />
            <ResizablePanel id="compared" order={2} defaultSize={50} minSize={20}>
              <ComparedPdf key={compared.studyId} reportId={reportId} study={compared} Viewer={Viewer} onClose={() => pane?.compare(null)} />
            </ResizablePanel>
          </>
        )}
      </ResizablePanelGroup>
    </section>
  );
}

interface ComparedPdfProps {
  /** The open report, left out of the study's reports. */
  reportId: number;
  study: ComparedStudy;
  Viewer: ComponentType<ReportPdfSlotProps>;
  onClose: () => void;
}

/**
 * The PDFs of the compared study's reports, one at a time: a tab each when it has more than one, with the study, the
 * shown report's download and a button to end the comparison.
 */
function ComparedPdf({ reportId, study, Viewer, onClose }: ComparedPdfProps) {
  const [reports, setReports] = useState<ReportPreviewDto[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [shownId, setShownId] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    getReportsByStudyId(study.studyId, STUDY_REPORTS_LIMIT)
      .then((page) => {
        if (cancelled) return;
        const others = page.items.filter((item) => item.reportId !== reportId);
        setReports(others);
        setShownId(others[0]?.reportId ?? null);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [study.studyId, reportId]);

  const shown = reports?.find((report) => report.reportId === shownId) ?? null;

  return (
    <section aria-label="Compared PDF" className="flex h-full min-h-0 flex-col">
      <header className="flex h-10 shrink-0 items-center gap-1 border-b bg-muted/40 px-3">
        <p className="min-w-0 flex-1 truncate text-sm" title={shown ? `${study.shortName}: ${shown.title}` : study.shortName}>
          <span className="font-medium">{study.shortName}</span>
          {shown && <span className="text-muted-foreground"> · {shown.title}</span>}
        </p>
        {shown && (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Download compared PDF"
                onClick={() => void downloadReportPdf(shown.reportId, shown.title)}
              >
                <Download />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Download PDF</TooltipContent>
          </Tooltip>
        )}
        <Tooltip>
          <TooltipTrigger asChild>
            <Button type="button" variant="ghost" size="icon-sm" aria-label="End comparison" onClick={onClose}>
              <X />
            </Button>
          </TooltipTrigger>
          <TooltipContent>End comparison</TooltipContent>
        </Tooltip>
      </header>
      {reports && reports.length > 1 && (
        <div role="tablist" aria-label={`Reports of ${study.shortName}`} className="flex shrink-0 gap-1 overflow-x-auto border-b px-2 py-1.5">
          {reports.map((report, index) => (
            <button
              key={report.reportId}
              type="button"
              role="tab"
              aria-selected={report.reportId === shownId}
              title={report.title}
              onClick={() => setShownId(report.reportId)}
              className={cn(
                "max-w-[14rem] shrink-0 truncate rounded-md px-2.5 py-1 text-xs transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
                report.reportId === shownId ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {index + 1}. {report.title}
            </button>
          ))}
        </div>
      )}
      <div className="min-h-0 flex-1">
        {shown ? (
          // Not in the report store: the viewer shows it without what extensions attach to the open reports.
          <Viewer key={shown.reportId} reportId={shown.reportId} title={shown.title} focus={null} />
        ) : (
          <p className="p-6 text-sm text-muted-foreground">
            {failed ? "The reports of the study could not be loaded." : reports === null ? "Loading reports…" : "This study has no other report."}
          </p>
        )}
      </div>
    </section>
  );
}

/** The PDF in the browser's own viewer. */
function BrowserPdfViewer({ reportId }: ReportPdfSlotProps) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;
    getReportPdf(reportId)
      .then((buffer) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(new Blob([buffer], { type: "application/pdf" }));
        setUrl(objectUrl);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [reportId]);

  if (url) return <iframe src={url} title="PDF" className="h-full w-full border-0" />;
  return (
    <p className="p-6 text-sm text-muted-foreground">{failed ? "The PDF could not be loaded." : "Loading PDF…"}</p>
  );
}
