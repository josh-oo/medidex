import type { ReactNode } from "react";
import { iconByName } from "@/lib/icons";

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
