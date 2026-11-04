import { StudyCardGraph } from "@/components/ui/study-view/study-graph";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Users,
  Calendar,
  Plus,
  Check,
} from "lucide-react";
import type { StudyDto } from "@/types/apiDTOs";
import type { ReactNode } from "react";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuTrigger,
} from "@/components/ui/context-menu";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { StudyContextMenuSlot, useStudyCardClassName } from "@/context/study-report-slots-context";
import { cn } from "@/lib/utils";

interface StudyCardProps extends StudyDto {
  /** Omitted for globally searched studies, which carry no relevance score. */
  relevance?: number | null;
  isAssigned: boolean;
  badge?: ReactNode;
  /** Report the card is shown for; lets extensions style it per report. */
  reportId?: number;
  /** The details of the study are folded out below the card. */
  expanded?: boolean;
  /** The folded-out details. */
  details?: ReactNode;
  onClick: (study: StudyDto) => void;
  onAssign: (study: StudyDto) => void;
}

const formatParticipantCount = (value?: string | null) => {
  if (!value) return "-";
  const numericValue = Number(value.replace(/,/g, ""));
  if (Number.isFinite(numericValue)) {
    return numericValue.toLocaleString();
  }
  return value;
};

const getRelevanceStroke = (relevance: number) => {
  if (relevance >= 0.9) return "stroke-emerald-500";
  if (relevance >= 0.7) return "stroke-blue-500";
  if (relevance >= 0.5) return "stroke-amber-500";
  return "stroke-orange-500";
};

const RING_RADIUS = 15;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

/** The relevance as a ring around its percentage; a plain ring for studies without one. */
function RelevanceRing({ relevance }: { relevance?: number | null }) {
  const hasRelevance = typeof relevance === "number";
  const percent = hasRelevance ? Math.round(relevance * 100) : null;
  const ring = (
    <div className="relative h-10 w-10 shrink-0">
      <svg viewBox="0 0 36 36" className="h-10 w-10 -rotate-90" aria-hidden="true">
        <circle cx="18" cy="18" r={RING_RADIUS} fill="none" strokeWidth="3" className="stroke-border" />
        {hasRelevance && (
          <circle
            cx="18"
            cy="18"
            r={RING_RADIUS}
            fill="none"
            strokeWidth="3"
            strokeLinecap="round"
            strokeDasharray={RING_CIRCUMFERENCE}
            strokeDashoffset={RING_CIRCUMFERENCE * (1 - relevance)}
            className={getRelevanceStroke(relevance)}
          />
        )}
      </svg>
      <span className="absolute inset-0 grid place-items-center text-[11px] font-semibold tabular-nums">
        {percent ?? "–"}
      </span>
    </div>
  );

  if (!hasRelevance) return ring;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{ring}</TooltipTrigger>
        <TooltipContent>
          <p>Relevance {percent}%</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

export function StudyCard({
  relevance,
  isAssigned,
  badge,
  reportId,
  expanded = false,
  details,
  onClick,
  onAssign,
  ...study
}: StudyCardProps) {
  const extensionClassName = useStudyCardClassName({ reportId, studyId: study.studyId });
  const hasContextMenu = useExtensionRegistry().studyContextMenuItems.length > 0;

  const card = (
    <div
      className={cn(
        "relative w-full max-w-full overflow-hidden rounded-xl border border-transparent bg-muted/60 transition-colors hover:bg-muted",
        expanded && "bg-muted",
        extensionClassName,
      )}
    >
      <div
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        aria-label={`${expanded ? "Hide" : "Show"} details for ${study.shortName}`}
        onClick={() => onClick(study)}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onClick(study);
          }
        }}
        className="flex cursor-pointer items-center gap-3 p-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 rounded-xl"
      >
        <RelevanceRing relevance={relevance} />

        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex min-w-0 items-center gap-2">
            <h3 className="truncate text-sm font-semibold" title={study.shortName}>
              {study.shortName}
            </h3>
            <div className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground whitespace-nowrap">
              {badge}
            </div>
          </div>

          {/* The aspects of the study on one line, each behind its own icon */}
          <div className="flex min-w-0 items-center gap-x-3 text-xs text-muted-foreground whitespace-nowrap">
            <span className="flex shrink-0 items-center gap-1" title="Participants">
              <Users className="h-3 w-3" />
              {formatParticipantCount(study.numberParticipants)}
            </span>
            <span className={cn("flex shrink-0 items-center gap-1", !study.duration && "text-muted-foreground/50")} title="Duration">
              <Calendar className="h-3 w-3" />
              {study.duration || "No duration"}
            </span>
            {/* The relations of the study that are shown on its card (e.g. the comparison of its arms) */}
            <StudyCardGraph studyId={study.studyId} />
          </div>
        </div>

        {/* Fixed width, so the button keeps its size when it turns into "Linked" */}
        <Button
          type="button"
          size="sm"
          variant={isAssigned ? "secondary" : "outline"}
          aria-pressed={isAssigned}
          disabled={isAssigned}
          onClick={(event) => {
            event.stopPropagation();
            if (!isAssigned) onAssign(study);
          }}
          className={cn(
            "w-24 shrink-0 bg-card",
            isAssigned &&
              "disabled:opacity-100 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
          )}
        >
          {isAssigned ? <Check /> : <Plus />}
          {isAssigned ? "Linked" : "Link"}
        </Button>
      </div>

      {expanded && details && (
        <div className="border-t border-border/70 bg-card">{details}</div>
      )}
    </div>
  );

  if (!hasContextMenu) return card;

  return (
    <ContextMenu>
      <ContextMenuTrigger asChild>{card}</ContextMenuTrigger>
      <ContextMenuContent>
        <StudyContextMenuSlot reportId={reportId} study={study} />
      </ContextMenuContent>
    </ContextMenu>
  );
}
