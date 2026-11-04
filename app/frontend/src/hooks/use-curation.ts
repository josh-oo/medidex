import { useCallback, useEffect, useState } from "react";
import { getProjects, getTasks } from "@/lib/api/projectApi";
import { getUserNamesByIds, listUsers } from "@/lib/api/adminApi";
import { useAuthStore } from "@/hooks/use-auth";
import type { ProjectDto, TaskDto } from "@/types/apiDTOs";
import type { UserDto } from "@/types/user/user.dto";

export interface Curation {
  loading: boolean;
  isAdmin: boolean;
  /** The projects (admins only). */
  projects: ProjectDto[];
  /** The projects the user is assigned to. */
  tasks: TaskDto[];
  ownerNameById: Map<string, string>;
  /** The users a project can be assigned to (admins only). */
  assignableUsers: UserDto[];
  refresh: () => void;
  removeProject: (projectId: string) => void;
}

type CurationData = Pick<Curation, "projects" | "tasks" | "ownerNameById" | "assignableUsers">;

// The last data loaded, by user: a page that comes back (e.g. the search, or the database management after a project)
// shows it at once and refreshes it in the background, instead of loading from nothing again.
let cache: { userKey: string; data: CurationData } | null = null;

/** The projects and tasks of the current user, for the curation overviews. */
export function useCuration(): Curation {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.isAdmin ?? false;
  const userKey = `${user?.id ?? ""}|${isAdmin}`;
  const cached = cache?.userKey === userKey ? cache.data : null;

  const [loading, setLoading] = useState(cached === null);
  const [projects, setProjects] = useState<ProjectDto[]>(cached?.projects ?? []);
  const [tasks, setTasks] = useState<TaskDto[]>(cached?.tasks ?? []);
  const [ownerNameById, setOwnerNameById] = useState<Map<string, string>>(cached?.ownerNameById ?? new Map());
  const [assignableUsers, setAssignableUsers] = useState<UserDto[]>(cached?.assignableUsers ?? []);

  const loadData = useCallback(
    async (cancelledRef?: { current: boolean }) => {
      const [projectsResult, tasksResult, users] = await Promise.all([
        isAdmin
          ? getProjects().catch((error) => {
              console.error("Failed to fetch projects:", error);
              return [] as ProjectDto[];
            })
          : Promise.resolve([] as ProjectDto[]),
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

      cache = {
        userKey,
        data: { projects: projectsResult, tasks: tasksResult, ownerNameById: ownerNames, assignableUsers: users },
      };
      if (cancelledRef?.current) return;
      setProjects(projectsResult);
      setTasks(tasksResult);
      setOwnerNameById(ownerNames);
      setAssignableUsers(users);
      setLoading(false);
    },
    [isAdmin, userKey]
  );

  useEffect(() => {
    const cancelledRef = { current: false };
    void loadData(cancelledRef);
    return () => {
      cancelledRef.current = true;
    };
  }, [loadData]);

  const refresh = useCallback(() => {
    void loadData();
  }, [loadData]);

  const removeProject = useCallback((projectId: string) => {
    setProjects((prev) => prev.filter((project) => project.projectId !== projectId));
    setTasks((prev) => prev.filter((task) => task.projectId !== projectId));
    if (cache) {
      const { data } = cache;
      cache = {
        ...cache,
        data: {
          ...data,
          projects: data.projects.filter((project) => project.projectId !== projectId),
          tasks: data.tasks.filter((task) => task.projectId !== projectId),
        },
      };
    }
  }, []);

  return { loading, isAdmin, projects, tasks, ownerNameById, assignableUsers, refresh, removeProject };
}
