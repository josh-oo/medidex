import type { ReactNode } from "react";
import { FolderOpen } from "lucide-react";
import type { CurationStep } from "@/lib/curation-steps";
import { StepChain } from "./step-chain";

interface CurationRowProps {
  title: string;
  /** E.g. the number of reports and when the project was created. */
  subtitle: ReactNode;
  /** The steps a person works on; the rings the current user may act on lead to their pages. */
  steps: CurationStep[];
  /** The assignees, in a slot of fixed width: more of them never move the rings. */
  people?: ReactNode;
  /** The menu of the project, at the end. */
  menu?: ReactNode;
}

/**
 * A project in one row of the curation panel: its name, its assignees, the rings of the steps a person works on
 * (which are also its actions) and its menu. The columns have the same widths in every row, so the rings line up;
 * on a narrow screen the row wraps.
 */
export function CurationRow({ title, subtitle, steps, people, menu }: CurationRowProps) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 md:grid md:grid-cols-[minmax(0,1fr)_8rem_auto_2rem]">
      <div className="flex min-w-0 basis-full items-center gap-3 md:basis-auto">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-primary/10">
          <FolderOpen className="h-4 w-4 text-primary" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-col">
          <span className="truncate text-sm font-semibold">{title}</span>
          <span className="truncate text-xs text-muted-foreground">{subtitle}</span>
        </div>
      </div>
      <div className="flex min-w-0 justify-end">{people}</div>
      <StepChain steps={steps} />
      <div className="ml-auto flex justify-end md:ml-0">{menu}</div>
    </div>
  );
}
