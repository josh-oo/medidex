// The pages of a report's PDF as a strip of thumbnails; clicking one opens the whole PDF in a tab of its own.
import { useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import workerSrc from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url";
import { ExternalLink } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;

export const PAGE_RATIO = 1.414;

// Enough to see that it is the right paper and that it is complete; the rest is behind "more pages".
const MAX_PAGES = 12;

const TILE_CLASS =
  "group relative block shrink-0 overflow-hidden rounded-md shadow-sm ring-1 ring-border transition hover:shadow-md hover:ring-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function PdfPages({ url, onOpen, width = 120 }: { url: string; onOpen: () => void; width?: number }) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const size = { width, height: width * PAGE_RATIO };
  const placeholder = <Skeleton className="shrink-0" style={size} />;

  if (failed) {
    return (
      <button type="button" onClick={onOpen} className={TILE_CLASS}>
        <div className="flex flex-col items-center justify-center bg-muted/50 px-3 text-center" style={size}>
          <p className="text-sm font-medium">No preview</p>
          <p className="mt-1 text-xs text-muted-foreground">Click to open the PDF.</p>
        </div>
      </button>
    );
  }

  const shown = numPages === null ? 0 : Math.min(numPages, MAX_PAGES);

  return (
    <Document
      file={url}
      onLoadSuccess={({ numPages }) => setNumPages(numPages)}
      onLoadError={() => setFailed(true)}
      loading={placeholder}
      error=""
      className="flex gap-3"
    >
      {Array.from({ length: shown }, (_, index) => (
        <button
          key={index}
          type="button"
          onClick={onOpen}
          title={`Page ${index + 1} of ${numPages} - open the full PDF`}
          className={TILE_CLASS}
        >
          <Page
            pageNumber={index + 1}
            width={width}
            renderTextLayer={false}
            renderAnnotationLayer={false}
            loading={placeholder}
          />
          <span className="absolute bottom-1 right-1 rounded bg-background/90 px-1.5 text-[10px] font-medium tabular-nums text-muted-foreground shadow-sm">
            {index + 1}
          </span>
          <span className="absolute inset-0 flex items-center justify-center bg-background/60 opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
            <ExternalLink className="h-4 w-4" />
          </span>
        </button>
      ))}
      {numPages !== null && numPages > MAX_PAGES && (
        <button
          type="button"
          onClick={onOpen}
          className={`${TILE_CLASS} flex flex-col items-center justify-center gap-1 bg-muted/50 text-center`}
          style={size}
        >
          <span className="text-sm font-medium">+{numPages - MAX_PAGES} pages</span>
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <ExternalLink className="h-3 w-3" />
            Open full PDF
          </span>
        </button>
      )}
    </Document>
  );
}
