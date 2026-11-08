import type { ReactNode } from "react";
import { iconByName } from "@/lib/icons";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { TagDto } from "@/types/apiDTOs";

interface DetailRowProps {
  /** An icon name of the study schema (see iconByName). */
  icon: string;
  label: ReactNode;
  children: ReactNode;
}

/** A line of the study details: the label in a narrow column, the value next to it. Belongs in a `<dl>`. */
export function DetailRow({ icon, label, children }: DetailRowProps) {
  const Icon = iconByName(icon);
  return (
    <div className="grid grid-cols-[6.5rem_minmax(0,1fr)] items-baseline gap-3 px-4 py-1.5 sm:grid-cols-[8rem_minmax(0,1fr)]">
      <dt className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
        <Icon className="h-3 w-3 shrink-0 self-center" />
        <span className="truncate">{label}</span>
      </dt>
      <dd className="min-w-0 text-sm">{children}</dd>
    </div>
  );
}

/** The values of a detail as small chips. */
export function DetailChips({ values }: { values: string[] }) {
  return (
    <ul className="flex flex-wrap gap-1">
      {values.map((value, index) => (
        <li key={`${value}-${index}`} className="rounded-md bg-muted px-1.5 py-0.5 text-xs leading-snug">
          {value}
        </li>
      ))}
    </ul>
  );
}

const CHIP_CLASS = "rounded-md bg-muted px-1.5 py-0.5 text-xs leading-snug";

/** The tags of a detail as small chips, their acronym and labels shown on hovering one that has any. */
export function TagChips({ tags }: { tags: TagDto[] }) {
  return (
    <ul className="flex flex-wrap gap-1">
      {tags.map((tag, index) => {
        const labels = tag.labels ?? [];
        if (!tag.acronym && labels.length === 0) {
          return (
            <li key={`${tag.id}-${index}`} className={CHIP_CLASS}>
              {tag.keyword}
            </li>
          );
        }
        return (
          <Tooltip key={`${tag.id}-${index}`}>
            <TooltipTrigger asChild>
              <li className={`${CHIP_CLASS} cursor-default`}>{tag.keyword}</li>
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs">
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-2 gap-y-0.5">
                {tag.acronym && (
                  <>
                    <dt className="opacity-70">Acronym</dt>
                    <dd>{tag.acronym}</dd>
                  </>
                )}
                {labels.length > 0 && (
                  <>
                    <dt className="opacity-70">Labels</dt>
                    <dd>{labels.join(", ")}</dd>
                  </>
                )}
              </dl>
            </TooltipContent>
          </Tooltip>
        );
      })}
    </ul>
  );
}
