import type { ReactNode } from "react";
import { parseDate } from "@/components/ui/relative-time";
import type { CurationStep } from "@/lib/curation-steps";
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
}

/**
 * A project in one row of the curation panel: the day it was created, its name, its assignees, the rings of the steps a person works on
 * (which are also its actions) and its menu. The columns have the same widths in every row, so the rings line up;
 * on a narrow screen the row wraps.
 */
export function CurationRow({ title, createdAt, subtitle, steps, action, locked, outcome, people, menu }: CurationRowProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 md:grid md:grid-cols-[minmax(0,1fr)_8rem_auto_2rem]">
      <div className="flex min-w-0 basis-full items-center gap-3 md:basis-auto">
        <CalendarSheet date={createdAt} />
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-semibold tabular-nums">{updateLabel(title)}</span>
          <span className="truncate text-xs text-muted-foreground">{subtitle}</span>
        </div>
        {action && <div className="ml-3 flex min-w-0 items-center">{action}</div>}
      </div>
      <div className="flex min-w-0 justify-end">{people}</div>
      {outcome ? (
        // The rings stay, invisible, to give the outcome their width.
        <div className="grid">
          <StepChain steps={steps} className="invisible col-start-1 row-start-1" />
          <div className="col-start-1 row-start-1 flex items-center">{outcome}</div>
        </div>
      ) : (
        <StepChain steps={steps} locked={locked} />
      )}
      <div className="ml-auto flex justify-end md:ml-0">{menu}</div>
    </div>
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
