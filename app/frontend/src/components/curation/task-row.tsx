import RelativeTime from "@/components/ui/relative-time";
import { taskSteps } from "@/lib/curation-steps";
import type { TaskDto } from "@/types/apiDTOs";
import { CurationRow } from "./curation-row";

interface TaskRowProps {
  task: TaskDto;
  ownerName?: string;
}

/** A project as one of its assignees sees it: the reports they link, behind the ring of their linkage. */
export function TaskRow({ task, ownerName }: TaskRowProps) {
  const total = task.numberReportsTotal || task.numberReportsReadyForProcessing;

  return (
    <CurationRow
      title={task.name}
      createdAt={task.createdAt}
      subtitle={
        <>
          {total} reports · <RelativeTime date={task.createdAt} /> by {ownerName ?? task.owner}
        </>
      }
      steps={taskSteps(task)}
    />
  );
}
