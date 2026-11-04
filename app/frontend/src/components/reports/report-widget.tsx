import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ChevronDown, Download, ExternalLink, FileText, Flag, FlagOff } from "lucide-react";
import { toast } from "sonner";
import { Widget } from "@/components/ui/widget";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { FlagReportDialog, type FlagTarget } from "@/components/ui/report-view/flag-report-dialog";
import { ReportAssignedStudiesBadges } from "@/components/ui/study-view/report-assigned-studies-badges";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { ReportAbstractSlot, ReportCardExtrasSlot } from "@/context/study-report-slots-context";
import { useReportStore } from "@/hooks/use-report-store";
import { deleteReportFlagByReportId } from "@/lib/api/reportApi";
import { downloadReportPdf, openReportPdf } from "@/lib/report-pdf";
import { cn } from "@/lib/utils";
import { ReportWidgetSkeleton } from "./workbench-skeleton";

interface ReportWidgetProps {
  reportId: number;
  /** Curation views: flag the report and manage its linked studies. */
  editMode: boolean;
}

/** The open report: what it is, its abstract, its PDF and flag, and the studies it is linked to. */
export function ReportWidget({ reportId, editMode }: ReportWidgetProps) {
  const report = useReportStore((state) => state.reports[reportId]);
  const setReportFlag = useReportStore((state) => state.setFlag);
  // An extension rendering the abstract may have content for reports without one (e.g. extracted tags).
  const hasAbstractExtension = Boolean(useExtensionRegistry().reportAbstract);
  const [flagTarget, setFlagTarget] = useState<FlagTarget | null>(null);
  const [isDeletingFlag, setIsDeletingFlag] = useState(false);
  const [abstractOpen, setAbstractOpen] = useState(false);
  // Whether the closed abstract is cut off: without more to show, there is no "More".
  const [abstractClamped, setAbstractClamped] = useState(false);
  const abstractRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setAbstractOpen(false);
  }, [reportId]);

  // Measured while closed (open, nothing is cut off); the abstract of an extension may change its length later.
  useLayoutEffect(() => {
    const element = abstractRef.current;
    if (!element || abstractOpen) return;
    const measure = () => setAbstractClamped(element.scrollHeight > element.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    for (const child of element.children) observer.observe(child);
    return () => observer.disconnect();
  }, [abstractOpen, reportId, Boolean(report), report?.abstract]);

  const reportNumber = <span className="font-mono text-xs text-muted-foreground">#{reportId}</span>;
  // The same widget while the report is not in the store yet, so the card stays put when it arrives.
  if (!report) {
    return (
      <Widget title="Report" icon={FileText} actions={reportNumber}>
        <ReportWidgetSkeleton />
      </Widget>
    );
  }

  const flagMessage = report.flag?.trim() ?? "";
  const hasFlag = Boolean(flagMessage);
  const hasAbstract = Boolean(report.abstract) || hasAbstractExtension;
  const trialId = report.trialId ?? report.preliminaryTrialId;

  const handleDeleteFlag = async () => {
    setIsDeletingFlag(true);
    try {
      await deleteReportFlagByReportId(reportId);
      setReportFlag(reportId, undefined);
      toast.success("Flag deleted.");
    } catch (error) {
      console.error("Error deleting report flag:", error);
      toast.error("Could not delete your flag. Please try again.");
    } finally {
      setIsDeletingFlag(false);
    }
  };

  return (
    <Widget
      title="Report"
      icon={FileText}
      actions={reportNumber}
    >
      {/* The card stays when the next report opens (its height eases, see Widget); its content fades in. */}
      <div key={reportId} className="motion-safe:animate-in motion-safe:fade-in motion-safe:duration-200">
        <h1 className="text-lg font-semibold leading-snug tracking-tight text-balance">{report.title}</h1>
        <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-sm text-muted-foreground">
          {report.authors && report.authors.length > 0 && (
            <span className="min-w-0 break-words">{report.authors.join(", ")}</span>
          )}
          {report.year ? <span>{report.year}</span> : null}
          {trialId && <span className="font-mono text-xs leading-5">{trialId}</span>}
        </div>

        <div className="min-w-0">
          <ReportCardExtrasSlot reportId={report.reportId} extensions={report.extensions} />
        </div>

        {hasAbstract && (
          <div className="mt-3">
            <div
              ref={abstractRef}
              className={cn(
                "text-sm text-muted-foreground leading-relaxed whitespace-pre-wrap",
                !abstractOpen && "line-clamp-4"
              )}
            >
              <ReportAbstractSlot
                reportId={report.reportId}
                extensions={report.extensions}
                title={report.title}
                text={report.abstract}
              />
            </div>
            {(abstractClamped || abstractOpen) && (
              <button
                type="button"
                className="mt-1 inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
                aria-expanded={abstractOpen}
                onClick={() => setAbstractOpen((open) => !open)}
              >
                {abstractOpen ? "Less" : "More"}
                <ChevronDown className={cn("h-3 w-3 transition-transform", abstractOpen && "rotate-180")} />
              </button>
            )}
          </div>
        )}

        {editMode && hasFlag && (
          <div className="mt-3 flex items-start gap-2 rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/40 dark:text-amber-300">
            <Flag className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0 break-words">{flagMessage}</span>
          </div>
        )}

        {editMode && <ReportAssignedStudiesBadges report={report} />}

        {(report.hasPdf || editMode) && (
          <div className="mt-4 flex flex-wrap gap-2">
            {/* Related actions share one control: the PDF, and the flag. */}
            {report.hasPdf && (
              <ButtonGroup aria-label="PDF">
                <Button type="button" variant="ghost" size="sm" onClick={() => void openReportPdf(report.reportId)}>
                  <ExternalLink />
                  Open PDF
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => void downloadReportPdf(report.reportId, report.title)}
                >
                  <Download />
                  Download
                </Button>
              </ButtonGroup>
            )}
            {editMode && (
              <ButtonGroup aria-label="Flag">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setFlagTarget({ id: report.reportId, title: report.title })}
                >
                  <Flag />
                  {hasFlag ? "Edit flag" : "Flag"}
                </Button>
                {hasFlag && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={isDeletingFlag}
                    onClick={() => void handleDeleteFlag()}
                  >
                    <FlagOff />
                    {isDeletingFlag ? "Deleting flag..." : "Delete"}
                  </Button>
                )}
              </ButtonGroup>
            )}
          </div>
        )}

        {editMode && (
          <FlagReportDialog
            target={flagTarget}
            onClose={() => setFlagTarget(null)}
            onSaved={(savedReportId, message) => setReportFlag(savedReportId, message)}
          />
        )}
      </div>
    </Widget>
  );
}
