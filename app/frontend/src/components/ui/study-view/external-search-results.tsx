import { useMemo } from "react";
import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ExternalRecordDto, ExternalRecordsDto } from "@/types/apiDTOs";

const SOURCE_LABELS: Record<string, string> = { "ClinicalTrials.gov": "CT.gov" };
export const sourceLabel = (source: string) => SOURCE_LABELS[source] ?? source;

const chip = "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap";

/** The sources each record was found by, by its key. */
export function useFoundBy(results: ExternalRecordsDto | null) {
  return useMemo(() => {
    const sources = new Map<string, string[]>();
    for (const search of results?.searches ?? []) {
      for (const key of search.found) {
        const list = sources.get(key) ?? [];
        if (!list.includes(search.source)) sources.set(key, [...list, search.source]);
      }
    }
    return sources;
  }, [results]);
}

/** A record of the external search, as a row like those of the studies: its title links to the source. */
export function ExternalRecordRow({
  record,
  sources,
  studyNames,
}: {
  record: ExternalRecordDto;
  sources: string[];
  studyNames: Map<number, string>;
}) {
  const meta = [record.firstAuthor, record.year, record.venue].filter(Boolean).join(" · ");
  return (
    <div className="flex items-start gap-3 rounded-xl bg-muted/60 p-3 transition-colors hover:bg-muted">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <a
          href={record.url || undefined}
          target="_blank"
          rel="noopener noreferrer"
          className="line-clamp-2 text-sm font-semibold hover:underline"
        >
          {record.title || record.key}
        </a>
        {meta && <p className="truncate text-xs text-muted-foreground">{meta}</p>}
        <div className="flex flex-wrap items-center gap-1">
          {record.thisReport && <span className={cn(chip, "bg-background text-muted-foreground")}>This report</span>}
          {record.studyIds.map((id) => (
            <span key={id} className={cn(chip, "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300")}>
              In {studyNames.get(id) ?? `study ${id}`}
            </span>
          ))}
          {sources.length > 0 && (
            <span className="text-[11px] text-muted-foreground">{sources.map(sourceLabel).join(" · ")}</span>
          )}
        </div>
      </div>
      {record.url && <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />}
    </div>
  );
}
