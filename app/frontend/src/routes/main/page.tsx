import { useCallback, useEffect, useState } from "react";
import { getProjects, getTasks } from "@/lib/api/projectApi";
import { getUserNamesByIds, listUsers } from "@/lib/api/adminApi";
import { ProjectCard } from "./components/project-card";
import { TaskCard } from "./components/task-card";
import { Button } from "@/components/ui/button";
import { FileText, FolderKanban, ListChecks, Plus } from "lucide-react";
import type { ProjectDto, TaskDto } from "@/types/apiDTOs";
import type { UserDto } from "@/types/user/user.dto";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { useAuthStore } from "@/hooks/use-auth";
import { Spinner } from "@/components/ui/spinner";

export default function Home() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.isAdmin ?? false;

  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<ProjectDto[]>([]);
  const [tasks, setTasks] = useState<TaskDto[]>([]);
  const [ownerNameById, setOwnerNameById] = useState<Map<string, string>>(new Map());
  const [assignableUsers, setAssignableUsers] = useState<UserDto[]>([]);

  const loadData = useCallback(
    async (cancelledRef?: { current: boolean }) => {
      const [projectsResult, tasksResult, users] = await Promise.all([
        getProjects().catch((error) => {
          console.error("Failed to fetch projects:", error);
          return [] as ProjectDto[];
        }),
        getTasks().catch((error) => {
          console.error("Failed to fetch tasks:", error);
          return [] as TaskDto[];
        }),
        isAdmin
          ? listUsers().catch((error) => {
              console.error("Failed to fetch assignable users:", error);
              return [] as UserDto[];
            })
          : Promise.resolve([] as UserDto[]),
      ]);

      const ownerIds = Array.from(
        new Set(
          tasksResult
            .map((task) => task.owner)
            .filter((ownerId): ownerId is string => Boolean(ownerId))
        )
      );
      const ownerNames = ownerIds.length
        ? await getUserNamesByIds(ownerIds).catch((error) => {
            console.error("Failed to resolve owner names:", error);
            return new Map<string, string>();
          })
        : new Map<string, string>();

      if (cancelledRef?.current) return;
      setProjects(projectsResult);
      setTasks(tasksResult);
      setOwnerNameById(ownerNames);
      setAssignableUsers(users);
      setLoading(false);
    },
    [isAdmin]
  );

  useEffect(() => {
    const cancelledRef = { current: false };
    void loadData(cancelledRef);
    return () => {
      cancelledRef.current = true;
    };
  }, [loadData]);

  const refreshData = useCallback(() => {
    void loadData();
  }, [loadData]);

  const handleProjectDeleted = useCallback((projectId: string) => {
    setProjects((prev) => prev.filter((project) => project.projectId !== projectId));
    setTasks((prev) => prev.filter((task) => task.projectId !== projectId));
  }, []);

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  const emptyTaskMessage = isAdmin
    ? "Create a project and assign it to yourself."
    : "Ask an admin to assign you to a project.";

  const firstName = user?.name?.split(" ")[0];
  const createProjectButton = (
    <CreateProjectDialog
      onProjectCreated={refreshData}
      trigger={
        <Button className="gap-2">
          <Plus className="h-4 w-4" />
          Create project
        </Button>
      }
    />
  );

  return (
    <div className="flex-1 overflow-auto">
      <div className="px-4 pt-4 pb-10 md:px-8 md:pt-6 max-w-7xl mx-auto space-y-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            {firstName && <p className="text-sm text-muted-foreground">Hello {firstName}</p>}
            <h1 className="text-2xl font-semibold tracking-tight">
              {isAdmin ? "Tasks and projects" : "Your tasks"}
            </h1>
          </div>
          {isAdmin && projects.length > 0 && createProjectButton}
        </div>

        <section>
          <div className="mb-3 flex items-center gap-2">
            <ListChecks className="h-4 w-4 text-muted-foreground" />
            <h2 className="text-sm font-semibold">Continue where you left off</h2>
            <span className="rounded-full bg-muted px-2 text-xs tabular-nums text-muted-foreground">{tasks.length}</span>
          </div>

          {tasks.length === 0 ? (
            <div className="rounded-2xl border border-dashed bg-card/50 px-6 py-10 text-center">
              <p className="text-sm text-muted-foreground">{emptyTaskMessage}</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {tasks.map((task) => (
                <TaskCard
                  key={task.projectId}
                  task={task}
                  ownerName={ownerNameById.get(task.owner)}
                />
              ))}
            </div>
          )}
        </section>

        {isAdmin && (
          <section>
            <div className="mb-3 flex items-center gap-2">
              <FolderKanban className="h-4 w-4 text-muted-foreground" />
              <h2 className="text-sm font-semibold">Projects</h2>
              <span className="rounded-full bg-muted px-2 text-xs tabular-nums text-muted-foreground">{projects.length}</span>
            </div>

            {projects.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed bg-card/50 px-6 py-16 text-center">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                  <FileText className="h-6 w-6 text-primary" />
                </div>
                <h3 className="mb-1 text-lg font-semibold">No projects yet</h3>
                <p className="mb-6 max-w-sm text-sm text-muted-foreground">
                  A project is a batch of new reports to link to studies. Create one and upload its reports.
                </p>
                {createProjectButton}
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {projects.map((project, index) => (
                  <ProjectCard
                    key={project.projectId}
                    project={project}
                    index={index}
                    assignableUsers={assignableUsers}
                    onDeleted={handleProjectDeleted}
                    onProjectUpdate={refreshData}
                    onAssigneesChange={refreshData}
                  />
                ))}
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
