import { useEffect, useState } from "react";
import { ChevronDown, Download, ExternalLink, FileText, Flag, FlagOff } from "lucide-react";
import { toast } from "sonner";
import { Widget } from "@/components/ui/widget";
import { Button } from "@/components/ui/button";
import { FlagReportDialog, type FlagTarget } from "@/components/ui/report-view/flag-report-dialog";
import { ReportAssignedStudiesBadges } from "@/components/ui/study-view/report-assigned-studies-badges";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { ReportAbstractSlot, ReportCardExtrasSlot } from "@/context/study-report-slots-context";
import { useReportStore } from "@/hooks/use-report-store";
import { deleteReportFlagByReportId, getReportPdf } from "@/lib/api/reportApi";
import { cn } from "@/lib/utils";

interface ReportWidgetProps {
  reportId: number;
  /** Curation views: flag the report and manage its linked studies. */
  editMode: boolean;
}

const downloadReportPdf = async (reportId: number, reportTitle: string) => {
  try {
    // 1. Create a strictly Latin title to match the server request
    const safeTitle = reportTitle
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "") // Remove accents
      .replace(/[‐-―]/g, "-") // Normalize dashes (Fixes your index 88 crash)
      .replace(/[\\/:*?"<>|]+/g, "-")   // Remove illegal filename characters
      .replace(/[^ -~]/g, "")           // Strip any remaining non-Latin/Unicode characters
      .trim();

    // 2. Fetch the PDF with auth attached
    const buffer = await getReportPdf(reportId);
    const blob = new Blob([buffer], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;

    // 3. Trigger the safe download
    link.download = `${reportId} - ${safeTitle || "report"}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Error downloading report PDF:", error);
    toast.error("Could not download PDF. Please try again.");
  }
};

const openReportPdf = async (reportId: number) => {
  // Open the tab synchronously (still tied to the user gesture) so
  // browsers don't treat the later navigation as a blocked popup.
  // Note: "noopener" makes window.open() return null, which would
  // leave us with no reference to navigate once the PDF is fetched.
  const newTab = window.open("", "_blank");
  try {
    const buffer = await getReportPdf(reportId);
    const blob = new Blob([buffer], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    if (newTab) {
      // Navigating a popup's top-level location to a blob: URL renders
      // blank in some browsers (Safari in particular); embedding it in
      // the popup's own document works reliably everywhere instead.
      newTab.document.title = `Report ${reportId}`;
      const style = newTab.document.createElement("style");
      style.textContent = "html,body,embed{margin:0;height:100%;width:100%}";
      newTab.document.head.appendChild(style);
      const embed = newTab.document.createElement("embed");
      embed.src = url;
      embed.type = "application/pdf";
      newTab.document.body.appendChild(embed);
      newTab.focus();
    }
  } catch (error) {
    console.error("Error opening report PDF:", error);
    toast.error("Could not open PDF. Please try again.");
    newTab?.close();
  }
};

/** The open report: what it is, its abstract, its PDF and flag, and the studies it is linked to. */
export function ReportWidget({ reportId, editMode }: ReportWidgetProps) {
  const report = useReportStore((state) => state.reports[reportId]);
  const setReportFlag = useReportStore((state) => state.setFlag);
  // An extension rendering the abstract may have content for reports without one (e.g. extracted tags).
  const hasAbstractExtension = Boolean(useExtensionRegistry().reportAbstract);
  const [flagTarget, setFlagTarget] = useState<FlagTarget | null>(null);
  const [isDeletingFlag, setIsDeletingFlag] = useState(false);
  const [abstractOpen, setAbstractOpen] = useState(false);

  useEffect(() => {
    setAbstractOpen(false);
  }, [reportId]);

  if (!report) return null;

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
      actions={<span className="font-mono text-xs text-muted-foreground">#{report.reportId}</span>}
    >
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
          <button
            type="button"
            className="mt-1 inline-flex items-center gap-0.5 text-xs text-muted-foreground hover:text-foreground cursor-pointer"
            aria-expanded={abstractOpen}
            onClick={() => setAbstractOpen((open) => !open)}
          >
            {abstractOpen ? "Less" : "More"}
            <ChevronDown className={cn("h-3 w-3 transition-transform", abstractOpen && "rotate-180")} />
          </button>
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
          {report.hasPdf && (
            <>
              <Button type="button" variant="secondary" size="sm" onClick={() => void openReportPdf(report.reportId)}>
                <ExternalLink />
                Open PDF
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => void downloadReportPdf(report.reportId, report.title)}
              >
                <Download />
                Download
              </Button>
            </>
          )}
          {editMode && (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              onClick={() => setFlagTarget({ id: report.reportId, title: report.title })}
            >
              <Flag />
              {hasFlag ? "Edit flag" : "Flag"}
            </Button>
          )}
          {editMode && hasFlag && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={isDeletingFlag}
              onClick={() => void handleDeleteFlag()}
            >
              <FlagOff />
              {isDeletingFlag ? "Deleting flag..." : "Delete flag"}
            </Button>
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
    </Widget>
  );
}
