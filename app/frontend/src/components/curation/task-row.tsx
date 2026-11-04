import RelativeTime from "@/components/ui/relative-time";
import { taskSteps } from "@/lib/curation-steps";
import type { TaskDto } from "@/types/apiDTOs";
import { CommitAction } from "./commit-action";
import { CurationRow } from "./curation-row";

interface TaskRowProps {
  task: TaskDto;
  /** The names of the owner and of the assignees the task waits for. */
  userNameById: Map<string, string>;
  onCommitted?: () => void;
}

/**
 * A project as one of its assignees sees it: the reports they link, behind the ring of their linkage, and the commit
 * of their links of the reports they are done with.
 */
export function TaskRow({ task, userNameById, onCommitted }: TaskRowProps) {
  const ownerName = userNameById.get(task.owner);
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
      locked={task.committed}
      action={
        <CommitAction
          projectId={task.projectId}
          projectName={task.name}
          completed={task.numberReportsCompleted}
          committed={task.numberReportsCommitted}
          total={task.numberReportsTotal}
          done={task.committed}
          waitingFor={task.pendingAssignees.map((id) => userNameById.get(id) ?? "")}
          onCommitted={onCommitted}
        />
      }
    />
  );
}
