import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, ChevronRight, Globe, Info, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Widget } from "@/components/ui/widget";
import RelativeTime from "@/components/ui/relative-time";
import { getExternalRecordsByReportId } from "@/lib/api/reportApi";
import { cn } from "@/lib/utils";
import type { ExternalRecordDto, ExternalRecordsDto, ExternalSearchDto, StudyCandidateDto } from "@/types/apiDTOs";

interface ExternalRecordsProps {
  reportId: number;
  /** A study of the database the records belong to, as the study list shows it (to open and link it). */
  renderStudy: (study: StudyCandidateDto) => ReactNode;
}

// Records shown before "Show N more".
const RECORDS_SHOWN = 5;
// Below this share of title words, a record is not called alike.
const TITLE_ALIKE = 0.2;

const SOURCE_LABELS: Record<string, string> = { "ClinicalTrials.gov": "CT.gov" };
const sourceLabel = (source: string) => SOURCE_LABELS[source] ?? source;

const chip = "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium whitespace-nowrap";
const amber = "bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300";
const emerald = "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300";
const muted = "bg-muted text-muted-foreground";

/**
 * What PubMed, Europe PMC, ClinicalTrials.gov and OpenAlex know of the report's trial, so that a study described
 * elsewhere already is not created twice: the report's registry ids searched in every source, the studies of the
 * database the records belong to, and the records outside it with the facts that relate them to the report.
 */
export function ExternalRecords({ reportId, renderStudy }: ExternalRecordsProps) {
  const [data, setData] = useState<{ reportId: number; records: ExternalRecordsDto } | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [showAll, setShowAll] = useState(false);

  // Only the latest request may set the state: a refresh still running when another report opens is dropped.
  const latest = useRef(0);
  const load = useCallback(
    (refresh: boolean) => {
      const request = ++latest.current;
      const isLatest = () => request === latest.current;
      setLoading(true);
      setFailed(false);
      getExternalRecordsByReportId(reportId, refresh)
        .then((records) => isLatest() && setData({ reportId, records }))
        .catch(() => isLatest() && setFailed(true))
        .finally(() => isLatest() && setLoading(false));
    },
    [reportId]
  );

  useEffect(() => {
    setShowAll(false);
    load(false);
  }, [load]);

  const current = data?.reportId === reportId ? data.records : null;

  return (
    <Widget
      title="External records"
      icon={Globe}
      actions={
        <>
          {current && (
            <span className="text-xs text-muted-foreground">
              <RelativeTime date={current.searchedAt} />
            </span>
          )}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            aria-label="Search again"
            title="Search again"
            disabled={loading}
            onClick={() => load(true)}
          >
            <RotateCw className={cn("h-3.5 w-3.5", loading && "motion-safe:animate-spin")} />
          </Button>
        </>
      }
    >
      {current ? (
        <ExternalRecordsBody
          records={current}
          renderStudy={renderStudy}
          showAll={showAll}
          onShowAll={() => setShowAll(true)}
        />
      ) : failed ? (
        <p className="text-sm text-muted-foreground">The external sources could not be searched.</p>
      ) : (
        <div className="space-y-2" aria-hidden>
          <Skeleton className="h-4 w-3/5" />
          <Skeleton className="h-3 w-2/5" />
          <Skeleton className="h-12 w-full rounded-xl" />
        </div>
      )}
    </Widget>
  );
}

function ExternalRecordsBody({
  records: { trialIds, trialIdStudies, searches, records, studies },
  renderStudy,
  showAll,
  onShowAll,
}: {
  records: ExternalRecordsDto;
  renderStudy: (study: StudyCandidateDto) => ReactNode;
  showAll: boolean;
  onShowAll: () => void;
}) {
  const studyNames = useMemo(() => new Map(studies.map((s) => [s.studyId, s.shortName])), [studies]);
  const foundBy = useMemo(() => {
    const sources = new Map<string, string[]>();
    for (const search of searches) {
      for (const key of search.found) {
        const list = sources.get(key) ?? [];
        if (!list.includes(search.source)) sources.set(key, [...list, search.source]);
      }
    }
    return sources;
  }, [searches]);

  const thisReport = records.filter((r) => r.thisReport);
  const others = records.filter((r) => !r.thisReport);
  const unknownWithId = others.filter((r) => r.carriesTrialId && r.studyIds.length === 0);
  const unreachable = [...new Set(searches.filter((s) => s.error).map((s) => sourceLabel(s.source)))];
  const shown = showAll ? others : others.slice(0, RECORDS_SHOWN);

  const status: { tone: "warn" | "info" | "ok"; text: string } =
    unknownWithId.length > 0
      ? {
          tone: "warn",
          text: `${unknownWithId.length === 1 ? "1 record carries" : `${unknownWithId.length} records carry`} this trial's registry ID but belongs to no study of the database.`,
        }
      : studies.length > 0
        ? {
            tone: "info",
            text: `${studies.length === 1 ? "1 study" : `${studies.length} studies`} of the database ${studies.length === 1 ? "has" : "have"} a record found for this trial.`,
          }
        : trialIds.length > 0
          ? { tone: "ok", text: "Nothing outside the database carries this trial's registry ID." }
          : { tone: "info", text: "This report names no registry ID; searched by first author and title." };
  const StatusIcon = { warn: AlertTriangle, info: Info, ok: CheckCircle2 }[status.tone];

  return (
    <div className="space-y-3 text-sm">
      <p className="flex items-start gap-2">
        <StatusIcon
          className={cn(
            "mt-0.5 h-4 w-4 shrink-0",
            status.tone === "warn" ? "text-amber-600" : status.tone === "ok" ? "text-emerald-600" : "text-sky-600"
          )}
        />
        <span>{status.text}</span>
      </p>

      {trialIds.length > 0 && (
        <div className="space-y-1.5">
          {trialIds.map((trialId) => (
            <TrialIdRow
              key={trialId}
              trialId={trialId}
              searches={searches.filter((s) => s.kind === "id" && sameTrialId(s.query, trialId))}
              studyCount={trialIdStudies[trialId]?.length ?? 0}
            />
          ))}
        </div>
      )}

      {studies.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground">In this database</p>
          {studies.map((study) => renderStudy(study))}
        </div>
      )}

      {others.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Found elsewhere · {others.length}</p>
          <ul className="divide-y">
            {shown.map((record) => (
              <RecordRow
                key={record.key}
                record={record}
                sources={foundBy.get(record.key) ?? []}
                studyNames={studyNames}
              />
            ))}
          </ul>
          {!showAll && others.length > RECORDS_SHOWN && (
            <Button type="button" variant="ghost" size="sm" className="h-7 px-2 text-xs" onClick={onShowAll}>
              Show {others.length - RECORDS_SHOWN} more
            </Button>
          )}
        </div>
      )}

      {thisReport.length > 0 && (
        <p className="text-xs text-muted-foreground">
          The report itself was found by{" "}
          {[...new Set(thisReport.flatMap((r) => foundBy.get(r.key) ?? []))].map(sourceLabel).join(", ")}.
        </p>
      )}

      <SearchList searches={searches} />

      {unreachable.length > 0 && (
        <p className="text-xs text-muted-foreground">Not reachable: {unreachable.join(", ")}.</p>
      )}
    </div>
  );
}

const trialKey = (value: string) => value.replace(/[^a-z0-9]/gi, "").toUpperCase();
const sameTrialId = (query: string, trialId: string) => trialKey(query) === trialKey(trialId);

/** A registry id with one badge per source: its hits over every spelling, linked to the search. */
function TrialIdRow({ trialId, searches, studyCount }: { trialId: string; searches: ExternalSearchDto[]; studyCount: number }) {
  const bySource = new Map<string, { hits: number | null; url: string; found: number; error: boolean }>();
  for (const search of searches) {
    const entry = bySource.get(search.source) ?? { hits: null, url: search.url, found: 0, error: false };
    entry.hits = search.hits === null ? entry.hits : (entry.hits ?? 0) + search.hits;
    entry.url ||= search.url;
    entry.found += search.found.length;
    entry.error ||= search.error !== null;
    bySource.set(search.source, entry);
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <code className="mr-1 rounded bg-muted px-1.5 py-0.5 text-xs">{trialId}</code>
      <span className={cn(chip, studyCount > 0 ? emerald : muted)} title="Studies of the database with this registry ID">
        Database {studyCount}
      </span>
      {[...bySource].map(([source, entry]) => {
        const label = `${sourceLabel(source)} ${entry.error ? "–" : entry.hits ?? "?"}`;
        const tone = entry.found > 0 ? amber : muted;
        return entry.url ? (
          <a
            key={source}
            href={entry.url}
            target="_blank"
            rel="noopener noreferrer"
            className={cn(chip, tone, "hover:underline")}
            title="Open the search"
          >
            {label}
          </a>
        ) : (
          <span key={source} className={cn(chip, tone)} title={entry.error ? "Not reachable" : undefined}>
            {label}
          </span>
        );
      })}
    </div>
  );
}

function RecordRow({
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
    <li className="py-2 first:pt-0">
      <a
        href={record.url || undefined}
        target="_blank"
        rel="noopener noreferrer"
        className="line-clamp-2 font-medium hover:underline"
      >
        {record.title || record.key}
      </a>
      {meta && <p className="truncate text-xs text-muted-foreground">{meta}</p>}
      <div className="mt-1 flex flex-wrap items-center gap-1">
        {record.carriesTrialId && <span className={cn(chip, amber)}>Registry ID of this trial</span>}
        {record.studyIds.map((id) => (
          <span key={id} className={cn(chip, emerald)}>
            In {studyNames.get(id) ?? `study ${id}`}
          </span>
        ))}
        {record.sameFirstAuthor && <span className={cn(chip, muted)}>Same first author</span>}
        {record.titleOverlap >= TITLE_ALIKE && (
          <span className={cn(chip, muted)} title="Share of the distinctive words of both titles">
            Title {Math.round(record.titleOverlap * 100)}% alike
          </span>
        )}
        {sources.length > 0 && (
          <span className="text-[11px] text-muted-foreground">found by {sources.map(sourceLabel).join(", ")}</span>
        )}
      </div>
    </li>
  );
}

/** Every query sent, folded: what was searched where, with its hits. */
function SearchList({ searches }: { searches: ExternalSearchDto[] }) {
  const [open, setOpen] = useState(false);
  const sources = new Set(searches.map((s) => s.source));
  return (
    <div>
      <button
        type="button"
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <ChevronRight className={cn("h-3 w-3 motion-safe:transition-transform", open && "rotate-90")} />
        {searches.length} searches in {sources.size} sources
      </button>
      {open && (
        <ul className="mt-1.5 space-y-1">
          {searches.map((search, index) => (
            <li key={index} className="flex min-w-0 items-center gap-2 text-xs">
              <span className="w-14 shrink-0 text-muted-foreground">{sourceLabel(search.source)}</span>
              {search.url ? (
                <a href={search.url} target="_blank" rel="noopener noreferrer" className="min-w-0 truncate hover:underline">
                  <code>{search.query}</code>
                </a>
              ) : (
                <code className="min-w-0 truncate">{search.query}</code>
              )}
              <span className="ml-auto shrink-0 tabular-nums text-muted-foreground" title={search.error ?? undefined}>
                {search.error ? "not reachable" : search.hits ?? "?"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
