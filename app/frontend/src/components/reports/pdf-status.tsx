// Where the PDF of a report stands, as a dot in front of its title in the list of the PDF upload. An extension that
// processes the PDFs replaces it (pdfStatusDot of the registry) with the stages of that processing.
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { useReportStore } from "@/hooks/use-report-store";
import { cn } from "@/lib/utils";

export type StatusDotTone = "none" | "unavailable" | "busy" | "waiting" | "done" | "failed";

const TONES: Record<StatusDotTone, string> = {
  none: "bg-muted-foreground/30",
  // Hollow green: done, without a PDF.
  unavailable: "border-[1.5px] border-emerald-500 bg-transparent",
  busy: "bg-amber-500 motion-safe:animate-pulse",
  waiting: "bg-amber-500",
  done: "bg-emerald-500",
  failed: "bg-red-500",
};

/** A small dot of the traffic light of the PDFs; `title` says what it means. */
export function StatusDot({ tone, title, className }: { tone: StatusDotTone; title: string; className?: string }) {
  return (
    <span
      role="img"
      aria-label={title}
      title={title}
      className={cn("inline-block h-2 w-2 shrink-0 rounded-full", TONES[tone], className)}
    />
  );
}

/** The PDF of a report as the store knows it (an upload or "Not available" updates it at once). */
export function useReportPdfState(reportId: number) {
  const hasPdf = useReportStore((state) => state.reports[reportId]?.hasPdf ?? false);
  const pdfUnavailable = useReportStore((state) => state.reports[reportId]?.pdfUnavailable ?? false);
  return { hasPdf, pdfUnavailable };
}

export function PdfStatusDot({ projectId, reportId }: { projectId: string; reportId: number }) {
  const { pdfStatusDot: Override } = useExtensionRegistry();
  const { hasPdf, pdfUnavailable } = useReportPdfState(reportId);

  if (Override) {
    return <Override projectId={projectId} reportId={reportId} hasPdf={hasPdf} pdfUnavailable={pdfUnavailable} />;
  }
  if (pdfUnavailable) return <StatusDot tone="unavailable" title="Marked as not available" />;
  return hasPdf ? <StatusDot tone="done" title="Has a PDF" /> : <StatusDot tone="none" title="No PDF yet" />;
}
