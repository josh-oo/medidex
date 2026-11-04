import { Search, Sparkles } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Widget } from "@/components/ui/widget";

// Outlines of the workbench while its content loads. They take the size of what they stand in for, so that nothing
// jumps when it arrives: the real widgets' headers where those are known, pulsing bars for the content.

/** The content of the report widget: its title, authors, abstract and buttons. */
export function ReportWidgetSkeleton() {
  return (
    <div aria-hidden="true">
      <Skeleton className="h-5 w-11/12" />
      <Skeleton className="mt-1.5 h-5 w-2/3" />
      <Skeleton className="mt-2.5 h-3.5 w-1/2" />
      <div className="mt-4 space-y-2.5">
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-full" />
        <Skeleton className="h-3.5 w-3/4" />
      </div>
      <Skeleton className="mt-5 h-8 w-48 rounded-lg" />
    </div>
  );
}

// The studies a page of a study list shows (CandidateStudyTable), so a list waiting for its rows has their height.
export const STUDY_ROWS_PER_PAGE = 10;

/** A study of a list, as StudyCard shows it (and as tall): its ring, name and summary, and the button to link it. */
export function StudyRowSkeleton() {
  return (
    <div className="flex items-center gap-3 rounded-xl bg-muted/60 p-3">
      <Skeleton className="h-10 w-10 shrink-0 rounded-full" />
      <div className="min-w-0 flex-1 space-y-2">
        <Skeleton className="h-4 w-2/5" />
        <Skeleton className="h-3 w-4/5" />
      </div>
      <Skeleton className="h-8 w-24 shrink-0 rounded-full" />
    </div>
  );
}

/** The studies next to a report (CandidateStudyTable): the search, and the similar studies. */
export function StudyColumnSkeleton() {
  return (
    <div className="space-y-4 pb-20" aria-busy="true">
      <Widget title="Find a study" icon={Search}>
        <Skeleton className="h-9 w-full rounded-md" />
      </Widget>
      <Widget title="Similar studies" icon={Sparkles}>
        <div className="space-y-2">
          {Array.from({ length: STUDY_ROWS_PER_PAGE }, (_, index) => (
            <StudyRowSkeleton key={index} />
          ))}
        </div>
      </Widget>
    </div>
  );
}

/** Any other panel next to a report: a widget with a few rows. */
export function PanelSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true">
      <Widget>
        <Skeleton className="mb-4 h-4 w-32" />
        <div className="space-y-2">
          {Array.from({ length: 4 }, (_, index) => (
            <StudyRowSkeleton key={index} />
          ))}
        </div>
      </Widget>
    </div>
  );
}

/** The sidebar's report list (ReportList): its heading, search, filters and rows. */
export function ReportListSkeleton() {
  return (
    <div className="space-y-3 px-3 pt-4 pb-3" aria-hidden="true">
      <div className="flex h-8 items-center px-1">
        <Skeleton className="h-5 w-24" />
      </div>
      <Skeleton className="h-9 w-full rounded-md" />
      <div className="flex gap-1">
        <Skeleton className="h-7 w-16 rounded-full" />
        <Skeleton className="h-7 w-16 rounded-full" />
        <Skeleton className="h-7 w-16 rounded-full" />
      </div>
      <div className="space-y-2 pt-1">
        {Array.from({ length: 10 }, (_, index) => (
          <Skeleton key={index} className="h-9 w-full rounded-xl" />
        ))}
      </div>
    </div>
  );
}
