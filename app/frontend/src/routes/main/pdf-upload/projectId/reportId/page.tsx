import { isNotFound } from "@/lib/api/errors";
import { useState, useCallback, useRef, useEffect } from "react";
import { useParams } from "react-router-dom";
import {
  UploadSection,
  type UploadSectionHandle,
} from "@/components/ui/upload/upload-section";
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

import { ExternalLink, FileText, FileX, Link2, Trash2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Widget } from "@/components/ui/widget";
import { openReportPdf } from "@/lib/report-pdf";
import { PdfFirstPage } from "@/components/reports/pdf-first-page";
import { deleteReportPdf, getReportPdf, uploadPdf } from "@/lib/api/reportApi";
import { toast } from "sonner";

export default function PdfDetailsPage() {
  const { reportId } = useParams<{ reportId: string }>() as { reportId: string };

  const setHasPdf = useReportStore((state) => state.setHasPdf);
  const hasPdf = useReportStore(
    (state) => state.reports[Number(reportId)]?.hasPdf ?? false
  );

  const uploadSectionRef = useRef<UploadSectionHandle>(null);

  const [iframeKey, setIframeKey] = useState(0);

  // This route is only ever reached via the pdf-upload layout, which populates the store
  // from getProjectReportsIntake (ReportIntakeDto rows) before rendering it - so doi/
  // fulltextLinks are already here, no separate GET /reports/{id} needed.
  const report = useReportStore(
    (state) => state.reports[Number(reportId)] as ReportIntakeDto | undefined
  );

  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [pdfMissing, setPdfMissing] = useState(false);

  const handleNotAvailableClick = useCallback(async () => {
    try {
      await uploadPdf(Number(reportId), null);
      setHasPdf(Number(reportId), true);
      setIframeKey((k) => k + 1);
    } catch (error) {
      console.error('Error in Not Available button:', error);
      toast.error("Could not mark this report as not available. Please try again.");
    }
  }, [reportId, setHasPdf]);

  const handleDeletePdf = useCallback(async () => {
    try {
      await deleteReportPdf(Number(reportId));

      setHasPdf(Number(reportId), false);
      setIframeKey((k) => k + 1);
    } catch (error) {
      console.error("Error deleting PDF:", error);
      toast.error("Could not delete the PDF. Please try again.");
    }
  }, [reportId, setHasPdf]);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    setPdfMissing(false);
    // Not the last report's PDF while this one's loads (its URL is revoked by then).
    setPdfUrl(null);

    getReportPdf(Number(reportId))
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
  }, [reportId, iframeKey]);

  const handleUploadSuccess = useCallback(() => {
    setHasPdf(Number(reportId), true);
    setIframeKey((k) => k + 1); // force iframe reload
  }, [reportId, setHasPdf]);

  const reportIdNumber = Number(reportId);

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
        title="Upload PDF"
        icon={Upload}
        actions={
          <Button type="button" variant="ghost" size="sm" onClick={handleNotAvailableClick}>
            <FileX />
            Not available
          </Button>
        }
      >
        <UploadSection
          key={reportId}
          ref={uploadSectionRef}
          onUploadSuccess={handleUploadSuccess}
          disabled={false}
          showUploadButton={true}
          autoStart={false}
          allowedFileExtension=".pdf"
          hint="PDF files only"
          onUpload={(file) => uploadPdf(reportIdNumber, file)}
        />
      </Widget>

      <Widget
        title="PDF"
        icon={FileText}
        actions={
          pdfUrl && (
            <>
              <Button type="button" variant="ghost" size="sm" onClick={() => void openReportPdf(reportIdNumber)}>
                <ExternalLink />
                Open in new tab
              </Button>
              {hasPdf && (
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
              )}
            </>
          )
        }
      >
        {/* Without a PDF the note is there at once: the report says so before anything loads. */}
        {pdfMissing || !hasPdf ? (
          <div className="rounded-xl bg-muted/50 px-4 py-8 text-center">
            <p className="text-sm font-medium">No PDF yet</p>
            <p className="mt-1 text-xs text-muted-foreground">Upload one above, or mark it as not available.</p>
          </div>
        ) : pdfUrl ? (
          // Only the first page, to check the upload by; the whole PDF reads better in a tab of its own.
          <PdfFirstPage key={iframeKey} url={pdfUrl} onOpen={() => void openReportPdf(reportIdNumber)} />
        ) : (
          <Skeleton className="mx-auto h-[396px] w-[280px] rounded-md" />
        )}
      </Widget>
    </div>
  );
}
