import { Fragment } from "react";
import type { CurationStep } from "@/lib/curation-steps";
import { cn } from "@/lib/utils";
import { ProgressRing } from "./progress-ring";

// Consecutive steps of the same group run side by side and are stacked.
const groupSteps = (steps: CurationStep[]) =>
  steps.reduce<CurationStep[][]>((groups, step) => {
    const last = groups[groups.length - 1];
    if (last && step.group && last[0].group === step.group) last.push(step);
    else groups.push([step]);
    return groups;
  }, []);

/** The steps of a project as rings joined by lines; stacked steps join with a fork. */
export function StepChain({ steps, className }: { steps: CurationStep[]; className?: string }) {
  const groups = groupSteps(steps);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      {groups.map((group, index) => (
        <Fragment key={group[0].key}>
          {index > 0 && groups[index - 1].length === 1 && <span aria-hidden className="w-3 border-t border-border" />}
          {group.length === 1 ? (
            <ProgressRing step={group[0]} />
          ) : (
            <>
              <div className="flex flex-col gap-1.5">
                {group.map((step) => (
                  <ProgressRing key={step.key} step={step} size="sm" />
                ))}
              </div>
              {index < groups.length - 1 && (
                <svg width="14" height="70" viewBox="0 0 14 70" className="shrink-0 stroke-border" aria-hidden>
                  <path d="M0 16C7 16 7 35 14 35M0 54C7 54 7 35 14 35" fill="none" strokeWidth="1" />
                </svg>
              )}
            </>
          )}
        </Fragment>
      ))}
    </div>
  );
}

