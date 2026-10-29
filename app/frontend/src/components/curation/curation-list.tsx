import type { ReactNode } from "react";
import type { Curation } from "@/hooks/use-curation";
import { ProjectRow } from "./project-row";
import { TaskRow } from "./task-row";

/**
 * The curation panel: one row per project, divided by lines, below an optional header. An admin sees the project
 * (with the ring of the linkage leading to their own work when they are assigned too); the tasks of the other
 * projects get rows of their own. `empty` is shown when there is no row.
 */
export function CurationList({
  curation,
  header,
  empty,
}: {
  curation: Curation;
  header?: ReactNode;
  empty?: ReactNode;
}) {
  const { projects, tasks, ownerNameById, assignableUsers, refresh, removeProject } = curation;
  const otherTasks = tasks.filter((task) => !projects.some((project) => project.projectId === task.projectId));

  return (
    <section className="divide-y overflow-hidden rounded-2xl border bg-card shadow-xs">
      {header && <div className="flex items-center justify-between gap-3 px-4 py-2.5">{header}</div>}
      {projects.length + otherTasks.length === 0 && empty}
      {projects.map((project) => (
        <ProjectRow
          key={project.projectId}
          project={project}
          assignableUsers={assignableUsers}
          onDeleted={removeProject}
          onProjectUpdate={refresh}
          onAssigneesChange={refresh}
        />
      ))}
      {otherTasks.map((task) => (
        <TaskRow key={task.projectId} task={task} ownerName={ownerNameById.get(task.owner)} />
      ))}
    </section>
  );
}
