import Link from "next/link";
import type { ProjectTaskDto } from "@/types/apiDTOs";

interface TaskCardProps {
  task: ProjectTaskDto;
  ownerName?: string;
}

const clamp = (value: number, min = 0, max = Number.POSITIVE_INFINITY) => {
  if (Number.isNaN(value)) return min;
  return Math.min(Math.max(value, min), max);
};

export function TaskCard({ task, ownerName }: TaskCardProps) {
  const totalProcessable = clamp(task.project.numberReportsReadyForProcessing ?? 0);
  const processed = clamp(task.numberReportsProcessed ?? 0, 0, totalProcessable || Number.POSITIVE_INFINITY);
  const progressPercent = totalProcessable > 0 ? Math.round((processed / totalProcessable) * 100) : 0;
  const displayOwner = ownerName ?? task.project.owner;

  return (
    <Link
      href={`/projects/${task.project.projectId}`}
      className="block focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
    >
      <div className="group relative border bg-card p-5 transition hover:border-primary/40">

        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold leading-tight text-foreground truncate">
              {task.project.name}
            </h3>
            <p className="mt-1 text-xs text-muted-foreground truncate">Owner: {displayOwner}</p>
          </div>
          <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            {progressPercent}%
          </span>
        </div>

        <div className="mt-4">
          <div className="flex items-center justify-between text-sm font-medium">
            <span className="text-muted-foreground">My progress</span>
            <span className="text-foreground">
              {processed} / {totalProcessable}
            </span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      </div>
    </Link>
  );
}
