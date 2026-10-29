import { useState, type ReactNode } from "react";
import { PageLink } from "@/lib/page-transition";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { CurationStep } from "@/lib/curation-steps";
import { cn } from "@/lib/utils";

const RADIUS = 15;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

const arc = (count: number, total: number) =>
  `${total > 0 ? (count / total) * CIRCUMFERENCE : 0} ${CIRCUMFERENCE}`;

interface ProgressRingProps {
  step: CurationStep;
  size?: "sm" | "md";
  className?: string;
}

/**
 * One step as a ring around its icon: solid for the reports it has done, light for those the steps before have made
 * ready, the track for those still blocked. A step the current user may work on is a button to its page: its icon is
 * in the colour of the controls and it lights up under the pointer. The others show their progress and, when
 * clicked, why the user cannot do the step (`hint`).
 */
export function ProgressRing({ step, size = "md", className }: ProgressRingProps) {
  const Icon = step.icon;
  const actionable = Boolean(step.href);
  const label = actionable && step.action ? `${step.action} · ${step.detail}` : `${step.label} · ${step.detail}`;

  const ring = (
    <span
      className={cn(
        "relative grid shrink-0 place-items-center rounded-full transition-[background-color,transform]",
        size === "sm" ? "h-8 w-8" : "h-11 w-11",
        actionable && "group-hover:scale-105 group-hover:bg-primary/10",
        className
      )}
    >
      <svg viewBox="0 0 36 36" className="absolute inset-0 h-full w-full -rotate-90" aria-hidden="true">
        <circle cx="18" cy="18" r={RADIUS} fill="none" className="stroke-border" strokeWidth="3.5" />
        {/* An empty arc is left out: with round ends it would still draw a dot. */}
        {step.ready > 0 && (
          <circle
            cx="18"
            cy="18"
            r={RADIUS}
            fill="none"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeDasharray={arc(step.ready, step.total)}
            className="stroke-primary/25"
          />
        )}
        {step.done > 0 && (
          <circle
            cx="18"
            cy="18"
            r={RADIUS}
            fill="none"
            strokeWidth="3.5"
            strokeLinecap="round"
            strokeDasharray={arc(step.done, step.total)}
            className="stroke-primary"
          />
        )}
      </svg>
      <Icon
        className={cn(size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4", actionable ? "text-primary" : "text-muted-foreground")}
        aria-hidden
      />
    </span>
  );

  const tooltip = (
    <TooltipContent>
      <p>
        {label}
        {actionable && " →"}
      </p>
    </TooltipContent>
  );

  if (step.href) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <PageLink
              to={step.href}
              aria-label={label}
              className="group rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            >
              {ring}
            </PageLink>
          </TooltipTrigger>
          {tooltip}
        </Tooltip>
      </TooltipProvider>
    );
  }

  return <RingHint step={step} label={label} ring={ring} tooltip={tooltip} />;
}

// A ring the user cannot act on: a click opens one line that says why, with what they can do about it.
function RingHint({
  step,
  label,
  ring,
  tooltip,
}: {
  step: CurationStep;
  label: string;
  ring: ReactNode;
  tooltip: ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>
              <button
                type="button"
                aria-label={label}
                className="rounded-full focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
              >
                {ring}
              </button>
            </PopoverTrigger>
          </TooltipTrigger>
          {tooltip}
        </Tooltip>
      </TooltipProvider>
      <PopoverContent
        side="bottom"
        sideOffset={8}
        className="flex w-auto max-w-[calc(100vw-2rem)] items-center gap-3 rounded-2xl border bg-popover py-2 pl-3.5 pr-2 text-sm text-popover-foreground shadow-lg"
      >
        <Info className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
        <span className="whitespace-nowrap">{step.hint ?? "Nothing to do here yet."}</span>
        {step.hintAction ? (
          <Button
            size="sm"
            className="shrink-0"
            onClick={() => {
              step.hintAction?.run();
              setOpen(false);
            }}
          >
            {step.hintAction.label}
          </Button>
        ) : (
          // Keeps the line as tall as with a button.
          <span className="h-8" aria-hidden />
        )}
      </PopoverContent>
    </Popover>
  );
}
