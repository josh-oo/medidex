import type { ReactNode } from "react";
import type { Curation } from "@/hooks/use-curation";
import { ProjectRow } from "./project-row";
import { TaskRow } from "./task-row";

const newestFirst = (a: { createdAt: string }, b: { createdAt: string }) => b.createdAt.localeCompare(a.createdAt);

/**
 * The updates of a database, newest first, one row each and divided by lines. An admin sees the project (with the
 * ring of the linkage leading to their own work when they are assigned too); the tasks of the other projects get rows
 * of their own. `empty` is shown when there is no row.
 */
export function CurationList({ curation, empty }: { curation: Curation; empty?: ReactNode }) {
  const { projects, tasks, userNameById, assignableUsers, refresh, removeProject } = curation;
  const otherTasks = tasks.filter((task) => !projects.some((project) => project.projectId === task.projectId));

  if (projects.length + otherTasks.length === 0) return <>{empty}</>;
  return (
    <div className="divide-y">
      {[...projects].sort(newestFirst).map((project) => (
        <ProjectRow
          key={project.projectId}
          project={project}
          assignableUsers={assignableUsers}
          onDeleted={removeProject}
          onProjectUpdate={refresh}
          onAssigneesChange={refresh}
        />
      ))}
      {[...otherTasks].sort(newestFirst).map((task) => (
        <TaskRow key={task.projectId} task={task} userNameById={userNameById} onCommitted={refresh} />
      ))}
    </div>
  );
}
