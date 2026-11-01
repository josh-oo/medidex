// The first page of a report's PDF as a preview; clicking it opens the whole PDF in a tab of its own.
import { useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import workerSrc from "pdfjs-dist/legacy/build/pdf.worker.min.mjs?url";
import { ExternalLink } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;

const PAGE_WIDTH = 280;
const PAGE_RATIO = 1.414;

export function PdfFirstPage({ url, onOpen }: { url: string; onOpen: () => void }) {
  const [failed, setFailed] = useState(false);
  const placeholder = <Skeleton style={{ width: PAGE_WIDTH, height: PAGE_WIDTH * PAGE_RATIO }} />;

  if (failed) {
    return (
      <div className="rounded-xl bg-muted/50 px-4 py-8 text-center">
        <p className="text-sm font-medium">No preview</p>
        <p className="mt-1 text-xs text-muted-foreground">Open the PDF in a new tab to read it.</p>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onOpen}
      title="Open the full PDF"
      className="group relative mx-auto block overflow-hidden rounded-md shadow-sm ring-1 ring-border transition hover:shadow-md hover:ring-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      <Document file={url} onLoadError={() => setFailed(true)} loading={placeholder} error="">
        <Page
          pageNumber={1}
          width={PAGE_WIDTH}
          renderTextLayer={false}
          renderAnnotationLayer={false}
          loading={placeholder}
        />
      </Document>
      <span className="absolute inset-x-0 bottom-0 flex items-center justify-center gap-1.5 bg-background/90 py-2 text-xs font-medium opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
        <ExternalLink className="h-3.5 w-3.5" />
        Open full PDF
      </span>
    </button>
  );
}
