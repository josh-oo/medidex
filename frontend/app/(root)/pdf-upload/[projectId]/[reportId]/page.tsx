"use client";

import { useState, useCallback, useRef, useEffect, use } from "react";
import Link from "next/link";
import {
  UploadSection,
  type UploadSectionHandle,
} from "@/components/ui/upload/upload-section";
import { ReportSourcesDto } from "@/types/apiDTOs";
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

import {
  Upload,
  FileText,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";

interface PdfPageProps {
  params: Promise<{
    projectId: string;
    reportId: string;
  }>;
}

export default function PdfDetailsPage({ params }: PdfPageProps) {

  const { projectId, reportId } = use(params);

  const setHasPdf = useReportStore((state) => state.setHasPdf);
  const hasPdf = useReportStore(
    (state) => state.reports[Number(reportId)]?.hasPdf ?? false
  );

  const uploadSectionRef = useRef<UploadSectionHandle>(null);

  const [iframeKey, setIframeKey] = useState(0);

  const [links, setLinks] = useState<ReportSourcesDto | null>(null);
  const [linksLoading, setLinksLoading] = useState(true);
  const [linksError, setLinksError] = useState<string | null>(null);

  const handleNotAvailableClick = useCallback(async () => {
    try {
      const response = await fetch(`/api/meerkat/reports/${reportId}/pdf`, {
        method: "POST",
        cache: "no-store",
        headers: {
          "Cache-Control": "no-cache",
          Pragma: "no-cache",
        },
      });
      setHasPdf(Number(reportId), true);
      setIframeKey((k) => k + 1);
    } catch (error) {
      console.error('Error in Not Available button:', error);
    }
  }, [reportId, setHasPdf]);

  const handleDeletePdf = useCallback(async () => {
    try {
      const response = await fetch(`/api/meerkat/reports/${reportId}/pdf`, {
        method: "DELETE",
        cache: "no-store",
        headers: {
          "Cache-Control": "no-cache",
          Pragma: "no-cache",
        },
      });

      if (!response.ok) {
        throw new Error(await response.text() || "Failed to delete PDF.");
      }

      setHasPdf(Number(reportId), false);
      setIframeKey((k) => k + 1);
    } catch (error) {
      console.error("Error deleting PDF:", error);
    }
  }, [reportId, setHasPdf]);

  useEffect(() => {
    async function fetchLinks() {
      setLinksLoading(true);
      setLinksError(null);

      try {
        const res = await fetch(`/api/meerkat/reports/${reportId}/sources`);
        if (!res.ok) throw new Error("Failed to fetch links");

        const data = await res.json();
        setLinks(data);
      } catch (err: any) {
        setLinksError(err.message || "Error fetching links");
      } finally {
        setLinksLoading(false);
      }
    }

    fetchLinks();
  }, [reportId]);

  const handleUploadSuccess = useCallback(() => {
    setHasPdf(Number(reportId), true);
    setIframeKey((k) => k + 1); // force iframe reload
  }, [reportId, setHasPdf]);

  return (
    <div className="pt-4">
      <div className="px-4 pb-2 border-b border-border">
        <div className="flex items-center gap-2">
          <Upload className="h-6 w-6 text-primary" />
          <h2 className="text-xl font-semibold">Upload PDF</h2>
          {linksLoading ? (
            <span className="text-muted-foreground">Loading doi...</span>
          ) : linksError ? (
            <span className="text-red-600 dark:text-red-400">{linksError}</span>
          ) : links?.doi === "undefined" ? (
            <span className="text-muted-foreground">No doi found for this report.</span>
          ) : (
            <a target="_blank" href={`https://www.doi.org/${links?.doi}`} className="truncate max-w-xs" style={{ display: 'inline-block', verticalAlign: 'middle', color: 'inherit', textDecoration: 'none' }}>{links?.doi}</a>
          )}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            {hasPdf && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
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
                    <AlertDialogAction onClick={handleDeletePdf}>
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
            <Button onClick={handleNotAvailableClick}>
              Not Available
            </Button>
          </div>
        </div>
      </div>

      <div className="mb-3 p-4">

        {linksLoading ? (
          <div className="text-muted-foreground">Loading links...</div>
        ) : linksError ? (
          <div className="text-red-600 dark:text-red-400">{linksError}</div>
        ) : links?.links.length === 0 ? (
          <div className="text-muted-foreground">
            No links found for this report.
          </div>
        ) : (
          <div>
            {links?.links.map((link, idx) => (
              <div key={link + idx} className="flex items-center gap-2 mb-1">
                <FileText className="h-4 w-4 flex-shrink-0" />
                <Link
                  href={link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="truncate"
                  title={link}
                  style={{ maxWidth: "100%", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", color: 'inherit', textDecoration: 'none', display: 'inline-block', verticalAlign: 'middle' }}
                >
                  {link}
                </Link>
              </div>
            ))}
          </div>
        )}

    <div className="pt-4">
      <UploadSection
        ref={uploadSectionRef}
        onUploadSuccess={handleUploadSuccess}
        disabled={false}
        showUploadButton={true}
        autoStart={false}
        allowedFileExtension=".pdf"
        hint="PDF files only"
        uploadUrl={`/api/meerkat/reports/${reportId}/pdf`}
      />
      </div>

      {/* PDF Preview Section */}
      <div className="mt-6">
        <iframe
          key={iframeKey}
          src={`/api/meerkat/reports/${reportId}/pdf`}
          title="PDF Preview"
          width="100%"
          height="500px"
          style={{ border: "1px solid #ccc", borderRadius: "8px" }}
        />
      </div>
    </div>
  </div>
  );
}
