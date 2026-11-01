import { useId, useMemo } from "react";
import { Calendar, ChevronDown, Globe, Users } from "lucide-react";
import { relationText } from "@/components/ui/study-view/study-graph";
import { StudyDetails } from "@/components/ui/study-view/study-details";
import { useStudyGraph } from "@/hooks/use-study-graph";
import { useStudySchema } from "@/hooks/use-study-schema";
import { cn } from "@/lib/utils";
import type { StudyDto } from "@/types/apiDTOs";
import { Highlight } from "./study-search-bar";

const formatParticipants = (value: string | null) => {
  if (!value) return null;
  const count = Number(value.replace(/,/g, ""));
  return Number.isFinite(count) ? count.toLocaleString() : value;
};

interface StudyResultCardProps {
  study: StudyDto;
  /** What was searched for; marked in the card. */
  terms: string[];
  expanded: boolean;
  onToggle: () => void;
}

/** A study found by the search: what it compares and its key facts; its details and reports fold out. */
export function StudyResultCard({ study, terms, expanded, onToggle }: StudyResultCardProps) {
  const detailsId = useId();
  const { schema } = useStudySchema();
  const graph = useStudyGraph(study.studyId);
  const participants = formatParticipants(study.numberParticipants);

  const lines = useMemo(
    () =>
      schema && graph
        ? schema.graph.relations
            .filter((relation) => relation.card)
            .map((relation) => relationText(schema.graph, graph, relation))
            .filter(Boolean)
        : [],
    [schema, graph]
  );

  return (
    <article className="overflow-hidden rounded-2xl border bg-card shadow-xs">
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={detailsId}
        onClick={onToggle}
        className="flex w-full flex-col gap-2.5 px-5 py-4 text-left transition-colors hover:bg-muted/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/60"
      >
        <div className="flex w-full flex-wrap items-center gap-x-2.5 gap-y-1.5">
          <h3 className="text-base font-semibold">
            <Highlight text={study.shortName} terms={terms} />
          </h3>
          {study.trialId && (
            <span className="rounded-md bg-muted px-2 py-0.5 font-mono text-xs text-foreground/80">
              <Highlight text={study.trialId} terms={terms} />
            </span>
          )}
          {study.status && (
            <span className="rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium capitalize text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400">
              {study.status}
            </span>
          )}
          <ChevronDown
            className={cn("ml-auto h-4 w-4 shrink-0 text-muted-foreground transition-transform", expanded && "rotate-180")}
            aria-hidden
          />
        </div>

        {/* What the study compares */}
        {lines.map((line) => (
          <p key={line} className="text-sm leading-relaxed text-foreground/90">
            <Highlight text={line} terms={terms} />
          </p>
        ))}

        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <Users className="h-3.5 w-3.5" aria-hidden />
            {participants ? `${participants} participants` : "Participants unknown"}
          </span>
          <span className={cn("flex items-center gap-1.5", !study.duration && "text-muted-foreground/70")}>
            <Calendar className="h-3.5 w-3.5" aria-hidden />
            {study.duration || "No duration"}
          </span>
          {study.countries.length > 0 && (
            <span className="flex min-w-0 items-center gap-1.5">
              <Globe className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="truncate">{study.countries.join(", ")}</span>
            </span>
          )}
        </div>
      </button>

      {expanded && (
        <div id={detailsId} className="border-t">
          <StudyDetails study={study} isActive variant="inline" />
        </div>
      )}
    </article>
  );
}
