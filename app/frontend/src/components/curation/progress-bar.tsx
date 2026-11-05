import { ArrowRight, Lock } from "lucide-react";
import { PageLink } from "@/lib/page-transition";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { CurationStep } from "@/lib/curation-steps";
import { cn } from "@/lib/utils";

const percent = (count: number, total: number) => `${total > 0 ? (count / total) * 100 : 0}%`;

/**
 * One step as a wide bar, for a row with a single step (an assignee's linkage) where a ring would get lost: its icon
 * and name, its numbers, and below them the bar, solid for the reports it has done, light for those the steps before
 * have made ready, the track for those still blocked. A step the current user may work on leads to its page, like its
 * ring; once the user has committed their links, the bar is `locked`: grey, with a lock, and leads nowhere.
 */
export function ProgressBar({ step, locked = false, className }: { step: CurationStep; locked?: boolean; className?: string }) {
  const Icon = step.icon;
  const actionable = Boolean(step.href) && !locked;
  const label = locked
    ? `${step.label} · ${step.detail} · locked`
    : actionable && step.action
      ? `${step.action} · ${step.detail}`
      : `${step.label} · ${step.detail}`;

  const bar = (
    <span
      className={cn(
        "flex w-full items-center gap-3 rounded-xl border px-3 py-2 transition-colors",
        actionable && "group-hover:border-primary/40 group-hover:bg-primary/5",
        className
      )}
    >
      <span
        className={cn(
          "grid h-8 w-8 shrink-0 place-items-center rounded-full",
          actionable ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
        )}
      >
        {locked ? <Lock className="h-3.5 w-3.5" aria-hidden /> : <Icon className="h-4 w-4" aria-hidden />}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1.5">
        <span className="flex items-baseline justify-between gap-3 text-xs">
          <span className="truncate font-medium">{step.label}</span>
          <span className="shrink-0 tabular-nums text-muted-foreground">{step.detail}</span>
        </span>
        <span className="relative h-1.5 overflow-hidden rounded-full bg-border" aria-hidden>
          {!locked && (
            <span className="absolute inset-y-0 left-0 rounded-full bg-primary/25" style={{ width: percent(step.ready, step.total) }} />
          )}
          <span
            className={cn("absolute inset-y-0 left-0 rounded-full", locked ? "bg-muted-foreground/35" : "bg-primary")}
            style={{ width: percent(step.done, step.total) }}
          />
        </span>
      </span>
      {actionable && (
        <ArrowRight
          className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary"
          aria-hidden
        />
      )}
    </span>
  );

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {actionable ? (
            <PageLink
              to={step.href!}
              aria-label={label}
              className="group flex w-full rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            >
              {bar}
            </PageLink>
          ) : (
            <span tabIndex={0} aria-label={label} className="flex w-full rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/60">
              {bar}
            </span>
          )}
        </TooltipTrigger>
        <TooltipContent>
          <p>
            {label}
            {actionable && " →"}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
