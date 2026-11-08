import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { parseDate } from "@/components/ui/relative-time";
import type { CurationStep } from "@/lib/curation-steps";
import { PageLink } from "@/lib/page-transition";
import { ProgressBar } from "./progress-bar";
import { ProgressRing } from "./progress-ring";
import { StepChain } from "./step-chain";

interface CurationRowProps {
  title: string;
  /** When the project was created, shown as a calendar sheet. */
  createdAt: string;
  /** E.g. the number of reports and when the project was created. */
  subtitle: ReactNode;
  /** The steps a person works on; the rings the current user may act on lead to their pages. */
  steps: CurationStep[];
  /** What the user can do once they are done with their steps (e.g. commit), right after the name: it never moves
   * the rings. */
  action?: ReactNode;
  /** The user has committed their links: the rings look locked. */
  locked?: boolean;
  /** Shown instead of the rings once the steps are behind the project (e.g. the merge of a locked one), as wide as
   * they were. */
  outcome?: ReactNode;
  /** The assignees, in a slot of fixed width: more of them never move the rings. */
  people?: ReactNode;
  /** The menu of the project, at the end. */
  menu?: ReactNode;
  /** A row with one step (an assignee's) shows it as a wide bar across the columns of the people, the rings and the
   * menu instead, where a single ring would get lost. */
  bar?: boolean;
}

/**
 * A project in one row of the curation panel: the day it was created, its name, its assignees, the rings of the steps a person works on
 * (which are also its actions) and its menu. The columns have the same widths in every row, so the rings line up;
 * on a narrow screen the row stays one line: the rings open from an Actions button and the people are left to the menu.
 */
export function CurationRow({
  title,
  createdAt,
  subtitle,
  steps,
  action,
  locked,
  outcome,
  people,
  menu,
  bar,
}: CurationRowProps) {
  return (
    <div className="flex items-center gap-3 px-4 py-3 md:grid md:grid-cols-[minmax(0,1fr)_8rem_auto_2rem] md:gap-6">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <CalendarSheet date={createdAt} />
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-semibold tabular-nums">{updateLabel(title)}</span>
          <span className="truncate text-xs text-muted-foreground">{subtitle}</span>
        </div>
        {action && <div className="ml-3 flex min-w-0 items-center">{action}</div>}
      </div>
      {bar && steps.length === 1 ? (
        <div className="flex min-w-24 flex-1 md:col-span-3 md:col-start-2 md:min-w-[18rem]">
          <ProgressBar step={steps[0]} locked={locked} />
        </div>
      ) : (
        <>
          <div className="hidden min-w-0 justify-end md:flex">{people}</div>
          {outcome ? (
            // The rings stay, invisible, to give the outcome their width.
            <div className="hidden md:grid">
              <StepChain steps={steps} className="invisible col-start-1 row-start-1" />
              <div className="col-start-1 row-start-1 flex items-center">{outcome}</div>
            </div>
          ) : (
            <StepChain steps={steps} locked={locked} className="hidden md:flex" />
          )}
          {steps.length > 0 && (
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="shrink-0 gap-1 rounded-full md:hidden">
                  Actions
                  <ChevronDown className="h-3.5 w-3.5" aria-hidden />
                </Button>
              </PopoverTrigger>
              <PopoverContent
                align="end"
                className="w-64 rounded-2xl border bg-popover p-2 text-popover-foreground shadow-lg"
              >
                {outcome ? <div className="p-1">{outcome}</div> : <StepList steps={steps} locked={locked} />}
              </PopoverContent>
            </Popover>
          )}
          <div className="flex shrink-0 justify-end">{menu}</div>
        </>
      )}
    </div>
  );
}

// The steps one below the other, each ring with its name and progress; the name of a step the user may do leads to it,
// as its ring does.
function StepList({ steps, locked }: { steps: CurationStep[]; locked?: boolean }) {
  return (
    <ul className="flex flex-col gap-1">
      {steps.map((step) => {
        const text = (
          <>
            <span className="block truncate text-sm font-medium">
              {step.href && !locked ? (step.action ?? step.label) : step.label}
            </span>
            <span className="block truncate text-xs text-muted-foreground">{step.detail}</span>
          </>
        );
        return (
          <li key={step.key} className="flex items-center gap-3 rounded-xl px-1.5 py-1">
            <ProgressRing step={step} locked={locked} />
            {step.href && !locked ? (
              <PageLink
                to={step.href}
                className="min-w-0 flex-1 rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
              >
                {text}
              </PageLink>
            ) : (
              <span className="min-w-0 flex-1">{text}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

// "Update 7" as "#7"; other names as they are.
function updateLabel(name: string) {
  const number = /^Update (\d+)$/.exec(name)?.[1];
  return number ? `#${number}` : name;
}

// The day of a date on a small calendar sheet: the month above, the day below (the year, too, when it is not this one).
function CalendarSheet({ date }: { date: string }) {
  const day = parseDate(date);
  if (Number.isNaN(day.getTime())) return <span className="h-10 w-10 shrink-0 rounded-lg bg-primary/10" aria-hidden />;
  const thisYear = day.getFullYear() === new Date().getFullYear();

  return (
    <time
      dateTime={day.toISOString()}
      title={day.toLocaleDateString(undefined, { dateStyle: "full" })}
      className="flex h-10 w-10 shrink-0 flex-col overflow-hidden rounded-lg border bg-background text-center leading-none"
    >
      <span className="bg-primary/10 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-primary">
        {day.toLocaleDateString(undefined, { month: "short" })}
      </span>
      <span className="grid flex-1 place-items-center text-sm font-semibold tabular-nums">
        {day.getDate()}
        {!thisYear && (
          <span className="-mt-0.5 text-[8px] font-medium text-muted-foreground">{day.getFullYear()}</span>
        )}
      </span>
    </time>
  );
}
