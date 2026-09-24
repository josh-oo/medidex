import { useEffect, useState } from "react";
import { getProjects, getTasks } from "@/lib/api/projectApi";
import { getUserNamesByIds, listUsers } from "@/lib/api/adminApi";
import { ProjectCard } from "./components/project-card";
import { TaskCard } from "./components/task-card";
import { HomeHero } from "./components/home-hero";
import { QuickStats } from "./components/quick-stats";
import { FeaturesShowcase } from "./components/features-showcase";
import { Button } from "@/components/ui/button";
import { FileText, Plus } from "lucide-react";
import type { ProjectDetailsDto, ProjectTaskDto } from "@/types/apiDTOs";
import type { UserDto } from "@/types/user/user.dto";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { useAuthStore } from "@/hooks/use-auth";
import { Spinner } from "@/components/ui/spinner";

export default function Home() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.isAdmin ?? false;

  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<ProjectDetailsDto[]>([]);
  const [tasks, setTasks] = useState<ProjectTaskDto[]>([]);
  const [ownerNameById, setOwnerNameById] = useState<Map<string, string>>(new Map());
  const [assignableUsers, setAssignableUsers] = useState<UserDto[]>([]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      const [projectsResult, tasksResult] = await Promise.all([
        getProjects().catch((error) => {
          console.error("Failed to fetch projects:", error);
          return [] as ProjectDetailsDto[];
        }),
        getTasks().catch((error) => {
          console.error("Failed to fetch tasks:", error);
          return [] as ProjectTaskDto[];
        }),
      ]);

      const ownerIds = Array.from(
        new Set(
          tasksResult
            .map((task) => task.project.owner)
            .filter((ownerId): ownerId is string => Boolean(ownerId))
        )
      );
      const ownerNames = ownerIds.length
        ? await getUserNamesByIds(ownerIds).catch((error) => {
            console.error("Failed to resolve owner names:", error);
            return new Map<string, string>();
          })
        : new Map<string, string>();

      const users = isAdmin
        ? await listUsers().catch((error) => {
            console.error("Failed to fetch assignable users:", error);
            return [] as UserDto[];
          })
        : [];

      if (cancelled) return;
      setProjects(projectsResult);
      setTasks(tasksResult);
      setOwnerNameById(ownerNames);
      setAssignableUsers(users);
      setLoading(false);
    })();

    return () => {
      cancelled = true;
    };
  }, [isAdmin]);

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

  const totalReports = projects.reduce((sum, b) => sum + b.numberReportsTotal, 0);
  const totalEmbedded = projects.reduce((sum, b) => sum + b.numberReportsPreProcessed, 0);
  const totalAssigned = projects.reduce((sum, b) => sum + b.numberReportsReadyForReview, 0);

  return (
    <div className="flex-1 overflow-auto">
      <div className="absolute inset-0 -z-10 overflow-hidden pointer-events-none">
        <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-gradient-to-bl from-primary/[0.03] via-transparent to-transparent" />
        <div className="absolute bottom-0 left-0 w-[600px] h-[600px] bg-gradient-to-tr from-primary/[0.02] via-transparent to-transparent" />
      </div>

      <div className="p-4 md:px-8 md:py-6 max-w-7xl mx-auto">
        <HomeHero userName={user?.name || "there"} />

        <QuickStats
          totalProjects={projects.length}
          totalReports={totalReports}
          totalAssigned={totalAssigned}
          totalEmbedded={totalEmbedded}
        />

        <div className="mt-10">
          <div className="mb-5">
            <h2 className="text-xl font-semibold tracking-tight">Your Tasks</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Stay focused on the projects that need your attention right now.
            </p>
          </div>

          {tasks.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-muted-foreground/25 bg-muted/30 px-6 py-12 text-center">
              <p className="text-sm text-muted-foreground">{emptyTaskMessage}</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {tasks.map((task) => (
                <TaskCard
                  key={task.project.projectId}
                  task={task}
                  ownerName={ownerNameById.get(task.project.owner)}
                />
              ))}
            </div>
          )}
        </div>

        {isAdmin && (
          <div className="mt-10">
            <div className="flex items-center justify-between mb-5">
              <div>
                <h2 className="text-xl font-semibold tracking-tight">Your Projects</h2>
                <p className="text-sm text-muted-foreground mt-0.5">
                  Select a project to start linking the new reports to studies
                </p>
              </div>
              <CreateProjectDialog
                trigger={
                  <Button variant="outline" size="sm" className="gap-2">
                    <Plus className="h-4 w-4" />
                    <span className="hidden sm:inline">Create Project</span>
                  </Button>
                }
              />
            </div>

            {projects.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center border-2 border-dashed border-muted-foreground/20 bg-muted/30">
                <div className="w-16 h-16 bg-primary/10 flex items-center justify-center mb-5 rounded-full">
                  <FileText className="w-7 h-7 text-primary" />
                </div>
                <h2 className="text-xl font-semibold mb-2">No projects yet</h2>
                <p className="text-muted-foreground max-w-sm mb-6">
                  Create your first project to start analyzing reports and discovering study connections.
                </p>
                <CreateProjectDialog
                  trigger={
                    <Button>
                      <Plus className="mr-2 h-4 w-4" />
                      Create your first project
                    </Button>
                  }
                />
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {projects.map((project, index) => (
                  <ProjectCard
                    key={project.projectId}
                    project={project}
                    index={index}
                    assignableUsers={assignableUsers}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        <FeaturesShowcase />
      </div>
    </div>
  );
}
