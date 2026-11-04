import { isNotFound } from "@/lib/api/errors";
import { useState, useCallback, useRef, useEffect, type DragEvent } from "react";
import { useParams } from "react-router-dom";
import { UploadSection } from "@/components/ui/upload/upload-section";
import { ReportIntakeDto } from "@/types/apiDTOs";
import { useReportStore } from "@/hooks/use-report-store";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

import { ExternalLink, FileText, FileX, Link2, RotateCcw, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Widget } from "@/components/ui/widget";
import { openReportPdf } from "@/lib/report-pdf";
import { PAGE_RATIO, PdfPages } from "@/components/reports/pdf-pages";
import { useReportPdfState } from "@/components/reports/pdf-status";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { deleteReportPdf, getReportPdf, uploadPdf } from "@/lib/api/reportApi";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// The width of a page of the preview strip; the whole PDF opens in a tab of its own on a click.
const PREVIEW_WIDTH = 120;

export default function PdfDetailsPage() {
  const { projectId, reportId } = useParams<{ projectId: string; reportId: string }>() as {
    projectId: string;
    reportId: string;
  };
  const reportIdNumber = Number(reportId);

  const setHasPdf = useReportStore((state) => state.setHasPdf);
  const { hasPdf, pdfUnavailable } = useReportPdfState(reportIdNumber);
  const { pdfStatusPanel: StatusPanel } = useExtensionRegistry();

  // This route is only ever reached via the pdf-upload layout, which populates the store
  // from getProjectReportsIntake (ReportIntakeDto rows) before rendering it - so doi/
  // fulltextLinks are already here, no separate GET /reports/{id} needed.
  const report = useReportStore(
    (state) => state.reports[reportIdNumber] as ReportIntakeDto | undefined
  );

  const [previewKey, setPreviewKey] = useState(0);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfMissing, setPdfMissing] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [dragging, setDragging] = useState(false);
  const replaceInputRef = useRef<HTMLInputElement>(null);

  const hasFile = hasPdf && !pdfUnavailable;

  const handleNotAvailableClick = useCallback(async () => {
    try {
      await uploadPdf(reportIdNumber, null);
      setHasPdf(reportIdNumber, true, true);
    } catch (error) {
      console.error('Error in Not Available button:', error);
      toast.error("Could not mark this report as not available. Please try again.");
    }
  }, [reportIdNumber, setHasPdf]);

  // Removes the PDF, or the mark as not available: the report needs a PDF again.
  const handleDeletePdf = useCallback(async () => {
    try {
      await deleteReportPdf(reportIdNumber);
      setHasPdf(reportIdNumber, false);
    } catch (error) {
      console.error("Error deleting PDF:", error);
      toast.error(pdfUnavailable ? "Could not undo. Please try again." : "Could not delete the PDF. Please try again.");
    }
  }, [reportIdNumber, setHasPdf, pdfUnavailable]);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    setPdfMissing(false);
    // Not the last report's PDF while this one's loads (its URL is revoked by then).
    setPdfUrl(null);
    // Without a file there is nothing to fetch (a report marked as not available would get the placeholder).
    if (!hasFile) return;

    getReportPdf(reportIdNumber)
      .then((buffer) => {
        if (cancelled) return;
        const blob = new Blob([buffer], { type: "application/pdf" });
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
      })
      .catch((error) => {
        if (cancelled) return;
        setPdfUrl(null);
        if (isNotFound(error)) {
          setPdfMissing(true);
        } else {
          console.error("Error fetching report PDF:", error);
        }
      });

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [reportIdNumber, previewKey, hasFile]);

  const handleUploadSuccess = useCallback(() => {
    setHasPdf(reportIdNumber, true);
    setPreviewKey((k) => k + 1);
  }, [reportIdNumber, setHasPdf]);

  // A PDF dropped on the card (or picked with Replace) replaces the one there is.
  const replacePdf = useCallback(
    async (file: File | undefined) => {
      if (!file) return;
      if (!file.name.toLowerCase().endsWith(".pdf")) {
        toast.error("Only PDF files can be uploaded.");
        return;
      }
      setReplacing(true);
      try {
        await uploadPdf(reportIdNumber, file);
        handleUploadSuccess();
      } catch (error) {
        console.error("Error replacing PDF:", error);
        toast.error("Could not upload the PDF. Please try again.");
      } finally {
        setReplacing(false);
      }
    },
    [reportIdNumber, handleUploadSuccess]
  );

  const dropHandlers = {
    onDragOver: (event: DragEvent) => {
      event.preventDefault();
      setDragging(true);
    },
    onDragLeave: (event: DragEvent) => {
      // Only leaving the card, not moving between its children.
      if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
    },
    onDrop: (event: DragEvent) => {
      event.preventDefault();
      setDragging(false);
      void replacePdf(event.dataTransfer.files[0]);
    },
  };

  const showUpload = !hasFile || pdfMissing;

  return (
    // Room at the bottom for floating actions of extensions, as next to the studies.
    <div className="space-y-4 pb-20">
      <Widget title="Find the PDF" icon={Link2}>
        <div className="space-y-1.5 text-sm">
          {report?.doi ? (
            <a
              target="_blank"
              rel="noopener noreferrer"
              href={`https://www.doi.org/${report.doi}`}
              className="flex min-w-0 items-center gap-2 hover:underline"
            >
              <span className="shrink-0 font-mono text-xs text-muted-foreground">DOI</span>
              <span className="truncate">{report.doi}</span>
            </a>
          ) : (
            <p className="text-muted-foreground">No DOI found for this report.</p>
          )}
          {report && report.fulltextLinks.length === 0 ? (
            <p className="text-muted-foreground">No fulltext links found for this report.</p>
          ) : (
            report?.fulltextLinks.map((link, idx) => (
              <a
                key={link + idx}
                href={link}
                target="_blank"
                rel="noopener noreferrer"
                title={link}
                className="flex min-w-0 items-center gap-2 hover:underline"
              >
                <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">{link}</span>
              </a>
            ))
          )}
        </div>
      </Widget>

      <Widget
        title="PDF"
        icon={FileText}
        actions={
          pdfUnavailable ? (
            <Button type="button" variant="ghost" size="sm" onClick={handleDeletePdf}>
              <RotateCcw />
              Undo
            </Button>
          ) : showUpload ? (
            <Button type="button" variant="ghost" size="sm" onClick={handleNotAvailableClick}>
              <FileX />
              Not available
            </Button>
          ) : (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-destructive"
                  aria-label="Delete PDF"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Delete this PDF?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This will remove the PDF from the report. You can upload a new one afterward.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                  <AlertDialogAction onClick={handleDeletePdf}>Delete</AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )
        }
      >
        {showUpload ? (
          <div className="space-y-3">
            {pdfUnavailable && (
              <div className="rounded-xl bg-muted/50 px-4 py-3 text-sm">
                <p className="font-medium">Marked as not available</p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  The report goes on without a PDF. If you find one later, upload it here.
                </p>
                {/* An extension may still process the report without its PDF (e.g. on its title and abstract). */}
                {StatusPanel && (
                  <div className="mt-3">
                    <StatusPanel projectId={projectId} reportId={reportIdNumber} hasPdf={hasPdf} pdfUnavailable />
                  </div>
                )}
              </div>
            )}
            <UploadSection
              key={reportId}
              onUploadSuccess={handleUploadSuccess}
              allowedFileExtension=".pdf"
              hint="PDF files only"
              onUpload={(file) => uploadPdf(reportIdNumber, file)}
            />
          </div>
        ) : (
          <div {...dropHandlers}>
            <div className="flex flex-col gap-3 sm:flex-row">
              {/* The strip scrolls on its own, the drop zone stays in reach and takes the room the pages leave. Its padding keeps the
                  rings of the pages inside: the card clips at its content edges while its height eases. */}
              <div className="-my-1 min-w-0 shrink overflow-x-auto p-1">
                {pdfUrl ? (
                  <PdfPages
                    key={previewKey}
                    url={pdfUrl}
                    width={PREVIEW_WIDTH}
                    onOpen={() => void openReportPdf(reportIdNumber)}
                  />
                ) : (
                  <Skeleton
                    className="shrink-0 rounded-md"
                    style={{ width: PREVIEW_WIDTH, height: PREVIEW_WIDTH * PAGE_RATIO }}
                  />
                )}
              </div>
              <button
                type="button"
                disabled={replacing}
                onClick={() => replaceInputRef.current?.click()}
                className={cn(
                  "flex shrink-0 flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center text-sm text-muted-foreground transition-colors sm:flex-[1_0_11rem] sm:py-0",
                  dragging ? "border-primary bg-primary/5 text-foreground" : "border-border bg-muted/30 hover:bg-muted/60",
                  replacing && "cursor-wait opacity-70"
                )}
                style={{ minHeight: PREVIEW_WIDTH * PAGE_RATIO }}
              >
                {replacing ? <Spinner className="h-6 w-6" /> : <Upload className="h-6 w-6" />}
                <span>
                  <span className="font-semibold">{replacing ? "Uploading…" : "Replace"}</span>
                  {!replacing && (
                    <>
                      <br />
                      click or drop a PDF
                    </>
                  )}
                </span>
              </button>
              <input
                ref={replaceInputRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={(event) => {
                  void replacePdf(event.target.files?.[0]);
                  event.target.value = "";
                }}
              />
            </div>
            {/* The processing of the PDF, as a footer of the card. */}
            {StatusPanel && (
              <div className="mt-4 border-t pt-4">
                <StatusPanel projectId={projectId} reportId={reportIdNumber} hasPdf={hasPdf} pdfUnavailable={pdfUnavailable} />
              </div>
            )}
          </div>
        )}
      </Widget>
    </div>
  );
}
