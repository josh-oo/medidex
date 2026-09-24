"use client";

import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Users,
  Calendar,
  CheckCircle2,
  Plus,
  Link,
  Sparkles,
} from "lucide-react";
import type { StudyDto } from "@/types/apiDTOs";
import type { ReactNode } from "react";

interface StudyCardProps {
  study: StudyDto;
  /** Omitted for globally searched studies, which carry no relevance score. */
  relevance?: number | null;
  isLinked: boolean;
  /** Shown for search results that are also part of the recommendations. */
  alsoRecommended?: boolean;
  onClick: (study: StudyDto) => void;
  onLink: (study: StudyDto) => void;
  aiBadge?: ReactNode;
}

const formatParticipantCount = (value?: string | null) => {
  if (!value) return "-";
  const numericValue = Number(value.replace(/,/g, ""));
  if (Number.isFinite(numericValue)) {
    return numericValue.toLocaleString();
  }
  return value;
};

const getRelevanceColor = (relevance: number) => {
  if (relevance >= 0.9) return "bg-emerald-500";
  if (relevance >= 0.7) return "bg-blue-500";
  if (relevance >= 0.5) return "bg-amber-500";
  return "bg-orange-500";
};

const getRelevanceBadgeStyle = (relevance: number) => {
  if (relevance >= 0.9) return "bg-emerald-100 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400";
  if (relevance >= 0.7) return "bg-blue-100 text-blue-700 dark:bg-blue-950/50 dark:text-blue-400";
  if (relevance >= 0.5) return "bg-amber-100 text-amber-700 dark:bg-amber-950/50 dark:text-amber-400";
  return "bg-orange-100 text-orange-700 dark:bg-orange-950/50 dark:text-orange-400";
};

export function StudyCard({
  study,
  relevance,
  isLinked,
  alsoRecommended = false,
  onClick,
  onLink,
  aiBadge,
}: StudyCardProps) {
  const hasRelevance = typeof relevance === "number";

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`View details for ${study.shortName}`}
      onClick={() => onClick(study)}
      className="p-4 mb-2 bg-card hover:bg-muted/50 rounded-lg relative w-full max-w-full overflow-hidden transition-all duration-200 border border-border/60 hover:border-border group-hover:shadow-sm flex items-center gap-4"
    >
      {/* Left indicator bar with relevance color */}
      <div
        className={`${
          hasRelevance ? getRelevanceColor(relevance!) : "bg-muted-foreground/30"
        } rounded-l-lg h-full w-1 absolute left-0 top-0 bottom-0 transition-all`}
      ></div>

      <div
        onClick={(e) => e.stopPropagation()}
        className="h-full flex items-center justify-center"
      >
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-pressed={isLinked}
                aria-label={isLinked ? "Study linked" : "Link study"}
                disabled={isLinked}
                onClick={() => {
                  if (!isLinked) {
                    onLink(study);
                  }
                }}
                className={`p-1 rounded-full transition-colors ${
                  isLinked
                    ? "text-primary/70 cursor-default"
                    : "text-muted-foreground/60 hover:text-primary"
                }`}
              >
                {isLinked ? (
                  <Link className="h-6 w-6" />
                ) : (
                  <Plus className="h-6 w-6" />
                )}
              </button>
            </TooltipTrigger>
            <TooltipContent>
              {isLinked ? "Already linked" : "Link study"}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>

      <div className="flex flex-col gap-3">
        {/* Top row: Short Name and badges */}
        <div className="flex items-start gap-3">
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <h3 className="text-base font-semibold truncate max-w-full">
                    {study.shortName}
                  </h3>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{study.shortName}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <div className="flex items-center gap-1 text-xs text-muted-foreground whitespace-nowrap">
              {hasRelevance && (
                <Badge
                  variant="secondary"
                  className={`font-semibold text-xs px-2 py-0.5 ${getRelevanceBadgeStyle(relevance!)}`}
                >
                  Relevance {(relevance! * 100).toFixed(1)}%
                </Badge>
              )}
              {alsoRecommended && (
                <Badge
                  variant="secondary"
                  className="font-normal text-xs px-2 py-0.5 gap-1"
                >
                  <Sparkles className="h-3 w-3" />
                  Also recommended
                </Badge>
              )}
              {aiBadge}
            </div>
          </div>
        </div>

        {/* Bottom row: Participants, Duration, Comparison */}
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs w-full">
          {/* NumberParticipants */}
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <div className="p-0.5 rounded bg-blue-50 dark:bg-blue-950/30">
              <Users className="h-3 w-3 text-blue-600 dark:text-blue-400" />
            </div>
            <span>{formatParticipantCount(study.numberParticipants)} participants</span>
          </div>

          {/* Duration */}
          <div className="flex items-center gap-1.5 text-muted-foreground">
            <div className={`p-0.5 rounded ${study.duration ? "bg-emerald-50 dark:bg-emerald-950/30" : "bg-muted"}`}>
              <Calendar className={`h-3 w-3 ${study.duration ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground/50"}`} />
            </div>
            <span className={study.duration ? "" : "text-muted-foreground/50"}>
              {study.duration || "No duration"}
            </span>
          </div>

          {/* Comparison */}
          {study.comparison && (
            <div className="flex items-center gap-1.5 text-muted-foreground flex-1 min-w-0 basis-0 max-w-full overflow-hidden">
              <div className="p-0.5 rounded bg-violet-50 dark:bg-violet-950/30 shrink-0">
                <CheckCircle2 className="h-3 w-3 text-violet-600 dark:text-violet-400" />
              </div>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <span className="truncate block w-full max-w-full">
                      {study.comparison}
                    </span>
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    <p>{study.comparison}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
