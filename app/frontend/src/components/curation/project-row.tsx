import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { UserPlus, Check, Trash2, AlertTriangle, MoreHorizontal } from "lucide-react";
import RelativeTime from "@/components/ui/relative-time";
import type { ProjectDto, AssigneeDto } from "@/types/apiDTOs";
import type { UserDto } from "@/types/user/user.dto";
import {
  assignUserToProject,
  removeUserFromProject,
  deleteProjectById,
  streamProjectUpdates,
} from "@/lib/api/projectApi";
import {
  useAssigneeOptionsSlot,
  type AssigneeOption,
  type AssigneeOptionsGroup,
} from "@/context/assignee-options-context";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { useAuthStore } from "@/hooks/use-auth";
import { projectSteps, type CurationStep } from "@/lib/curation-steps";
import { CurationRow } from "./curation-row";

const EMPTY_USERS: UserDto[] = [];
// Avatars shown in the row; the rest is counted.
const MAX_AVATARS = 3;

interface ProjectRowProps {
  project: ProjectDto;
  assignableUsers?: UserDto[];
  onAssigneesChange?: (payload: { projectId: string; userIds: string[] }) => void;
  onDeleted?: (projectId: string) => void;
  onProjectUpdate?: (projectId: string) => void;
}

const getUserInitials = (name?: string) => {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts
    .map((part) => part.charAt(0).toUpperCase())
    .join("")
    .slice(0, 2);
};

/**
 * A project as an admin sees it: the rings of its steps (the ones the user may work on lead there: the owner uploads
 * PDFs and reviews, the assignees link), its assignees, and a menu to assign people or delete the project.
 */
export function ProjectRow({
  project,
  assignableUsers = EMPTY_USERS,
  onAssigneesChange,
  onDeleted,
  onProjectUpdate,
}: ProjectRowProps) {
  const userId = useAuthStore((s) => s.user?.id);
  const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Optimistic assignee ids shown after a toggle until the parent hands down a fresh
  // `project.assignees`; an override made against an older array is ignored.
  const [assigneeOverride, setAssigneeOverride] = useState<{
    base: ProjectDto["assignees"];
    ids: string[];
  } | null>(null);
  const [isAssignOpen, setIsAssignOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [pendingAssigneeId, setPendingAssigneeId] = useState<string | null>(null);
  const extraGroups = useAssigneeOptionsSlot(project.projectId);
  const { projectSteps: stepResolvers } = useExtensionRegistry();
  const assigneeIds = useMemo(
    () =>
      assigneeOverride?.base === project.assignees
        ? assigneeOverride.ids
        : (project.assignees ?? []).map((assignee) => assignee.userId),
    [assigneeOverride, project.assignees],
  );
  const isUpdatingAssignees = pendingAssigneeId !== null;

  useEffect(() => {
    const scheduleRefresh = () => {
      if (refreshTimeoutRef.current !== null) {
        clearTimeout(refreshTimeoutRef.current);
      }

      refreshTimeoutRef.current = setTimeout(() => {
        refreshTimeoutRef.current = null;
        onProjectUpdate?.(project.projectId);
      }, 200);
    };

    const stopStream = streamProjectUpdates(project.projectId, {
      onEvent: () => {
        scheduleRefresh();
      },
      onError: (error) => {
        console.error(`Project stream error for ${project.projectId}:`, error);
      },
    });

    return () => {
      if (refreshTimeoutRef.current !== null) {
        clearTimeout(refreshTimeoutRef.current);
        refreshTimeoutRef.current = null;
      }
      stopStream();
    };
  }, [project.projectId, onProjectUpdate]);

  const sortedUsers = useMemo(
    () => [...assignableUsers].sort((a, b) => a.email.localeCompare(b.email)),
    [assignableUsers],
  );

  const extraById = useMemo(() => {
    const map = new Map<string, { option: AssigneeOption; onToggle: AssigneeOptionsGroup["onToggle"] }>();
    extraGroups.forEach((group) =>
      group.options.forEach((option) => map.set(option.id, { option, onToggle: group.onToggle }))
    );
    return map;
  }, [extraGroups]);

  const knownUsers = useMemo(() => {
    const map = new Map<string, UserDto>();
    sortedUsers.forEach((user) => map.set(user.id, user));
    extraById.forEach(({ option }, id) => {
      if (!map.has(id)) {
        map.set(id, { id: option.id, name: option.name, email: "", roles: [], isApproved: true });
      }
    });
    return map;
  }, [sortedUsers, extraById]);

  const assigneeMap = useMemo(() => {
    const map = new Map<string, AssigneeDto>();
    (project.assignees ?? []).forEach((assignee) => map.set(assignee.userId, assignee));
    return map;
  }, [project.assignees]);

  const resolvedAssignees = assigneeIds.map((id) => ({
    userId: id,
    name: knownUsers.get(id)?.name ?? id,
    icon: extraById.get(id)?.option.icon,
    linkedReports: assigneeMap.get(id)?.numberReportsLinked ?? 0,
  }));

  const isOwner = Boolean(userId) && project.owner === userId;
  const isAssignee = Boolean(userId) && assigneeIds.includes(userId!);
  const steps = useMemo(() => {
    const extraSteps = stepResolvers
      .map((resolve) => resolve(project))
      .filter((step): step is CurationStep => step !== null);
    // The row shows the steps a person works on; the automatic ones run by themselves.
    return projectSteps(project, { isOwner, isAssignee }, extraSteps).filter((step) => step.manual);
  }, [project, stepResolvers, isOwner, isAssignee]);

  const toggleAssignee = useCallback(
    async (assigneeId: string) => {
      if (isUpdatingAssignees) {
        return;
      }
      const normalizedUserId = assigneeId.trim();
      if (!normalizedUserId) {
        return;
      }
      const isSelected = assigneeIds.includes(normalizedUserId);
      const customToggle = extraById.get(normalizedUserId)?.onToggle;

      setPendingAssigneeId(normalizedUserId);
      try {
        if (customToggle) {
          await customToggle(normalizedUserId, isSelected);
        } else if (isSelected) {
          await removeUserFromProject(project.projectId, normalizedUserId);
        } else {
          await assignUserToProject(project.projectId, normalizedUserId);
        }

        const next = isSelected
          ? assigneeIds.filter((id) => id !== normalizedUserId)
          : [...assigneeIds, normalizedUserId];
        setAssigneeOverride({ base: project.assignees, ids: next });
        onAssigneesChange?.({ projectId: project.projectId, userIds: next });
      } catch (error) {
        console.error(`Failed to update assignee ${normalizedUserId}`, error);
        window.alert(
          error instanceof Error
            ? error.message
            : "Unable to update project assignees. Please try again."
        );
      } finally {
        setPendingAssigneeId(null);
      }
    },
    [assigneeIds, isUpdatingAssignees, onAssigneesChange, project.projectId, project.assignees, extraById]
  );

  const handleDeleteProject = useCallback(async () => {
    if (isDeleting) return;

    setIsDeleting(true);
    try {
      await deleteProjectById(project.projectId);

      setIsDeleteDialogOpen(false);
      onDeleted?.(project.projectId);
    } catch (error) {
      console.error("Failed to delete project", error);
      window.alert("Unable to delete the update. Please try again or contact an administrator.");
    } finally {
      setIsDeleting(false);
    }
  }, [isDeleting, project.projectId, onDeleted]);

  const renderUserCommandItem = (user: { id: string; name: string }) => {
    const isSelected = assigneeIds.includes(user.id);
    const Icon = extraById.get(user.id)?.option.icon;
    const linked = assigneeMap.get(user.id)?.numberReportsLinked;
    return (
      <CommandItem
        key={user.id}
        disabled={isUpdatingAssignees}
        onSelect={() => {
          if (isUpdatingAssignees) return;
          void toggleAssignee(user.id);
        }}
        className="flex items-center gap-2"
      >
        <Avatar className="h-7 w-7 border border-border/70 bg-muted">
          <AvatarFallback className="text-[11px] font-semibold">
            {Icon ? <Icon className="h-3.5 w-3.5" aria-hidden /> : getUserInitials(user.name)}
          </AvatarFallback>
        </Avatar>
        <div className="flex-1 truncate">
          <p className="text-sm font-medium leading-tight truncate">{user.name}</p>
          {isSelected && linked !== undefined && (
            <p className="text-xs text-muted-foreground">
              {linked} / {project.numberReportsReadyForProcessing} linked
            </p>
          )}
        </div>
        {isSelected && <Check className="h-4 w-4 text-primary" />}
      </CommandItem>
    );
  };

  const assigneeNames = resolvedAssignees.map((assignee) => assignee.name).join(", ");
  // An admin who is not assigned can assign themselves from the hint of the linkage ring.
  const rowSteps = steps.map((step) =>
    step.key === "linkage" && !isAssignee && userId
      ? { ...step, hintAction: { label: "Assign me", run: () => void toggleAssignee(userId) } }
      : step
  );

  const people = (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={() => setIsAssignOpen(true)}
            aria-label={resolvedAssignees.length > 0 ? `Assigned: ${assigneeNames}. Change` : "Assign people"}
            className="flex h-11 items-center rounded-full px-1.5 transition-colors hover:bg-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
          >
            {resolvedAssignees.length > 0 ? (
              <span className="flex -space-x-2">
                {resolvedAssignees.slice(0, MAX_AVATARS).map(({ userId: id, name, icon: Icon }) => (
                  <Avatar key={id} className="h-9 w-9 border-2 border-card bg-muted">
                    <AvatarFallback className="text-xs font-semibold">
                      {Icon ? <Icon className="h-4 w-4" aria-hidden /> : getUserInitials(name)}
                    </AvatarFallback>
                  </Avatar>
                ))}
                {resolvedAssignees.length > MAX_AVATARS && (
                  <Avatar className="h-9 w-9 border-2 border-card bg-muted">
                    <AvatarFallback className="text-xs font-semibold">
                      +{resolvedAssignees.length - MAX_AVATARS}
                    </AvatarFallback>
                  </Avatar>
                )}
              </span>
            ) : (
              <span className="flex items-center gap-1.5 px-1 text-xs font-medium text-muted-foreground">
                <UserPlus className="h-4 w-4" aria-hidden />
                Assign
              </span>
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent>
          <p>{resolvedAssignees.length > 0 ? `Assigned: ${assigneeNames}` : "Nobody is assigned yet"}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );

  const menu = (
    <>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon-sm" aria-label={`More for ${project.name}`}>
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <DropdownMenuItem onSelect={() => setIsAssignOpen(true)}>
            <UserPlus className="h-4 w-4" />
            Assign people…
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" onSelect={() => setIsDeleteDialogOpen(true)}>
            <Trash2 className="h-4 w-4" />
            Delete update…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <Dialog open={isAssignOpen} onOpenChange={setIsAssignOpen}>
        <DialogContent className="max-w-sm p-0">
          <DialogHeader className="px-4 pt-4">
            <DialogTitle>Assign people</DialogTitle>
            <DialogDescription>The assignees link the reports of {project.name} to their studies.</DialogDescription>
          </DialogHeader>
          <Command className="border-t">
            <CommandInput placeholder="Search users..." />
            <CommandList className="max-h-72 overflow-y-auto">
              <CommandEmpty>No users found.</CommandEmpty>
              {extraGroups.map((group) =>
                group.options.length > 0 ? (
                  <CommandGroup key={group.heading} heading={group.heading}>
                    {group.options.map(renderUserCommandItem)}
                  </CommandGroup>
                ) : null
              )}
              {sortedUsers.length > 0 && (
                <CommandGroup heading="Team">{sortedUsers.map(renderUserCommandItem)}</CommandGroup>
              )}
            </CommandList>
          </Command>
        </DialogContent>
      </Dialog>

      <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <AlertDialogContent className="sm:max-w-md">
          <AlertDialogHeader>
            <div className="mb-2 flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-4 w-4" aria-hidden />
              <span className="text-xs font-semibold uppercase tracking-wide">Danger Zone</span>
            </div>
            <AlertDialogTitle>Delete update?</AlertDialogTitle>
            <AlertDialogDescription>This will permanently remove all data for this update, its reports included.</AlertDialogDescription>
            <div className="mt-2 rounded-lg bg-muted/50 px-3 py-2 text-sm text-foreground">{project.name}</div>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2 sm:gap-2">
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteProject}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? "Deleting..." : "Delete update"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );

  return (
    <CurationRow
      title={project.name}
      createdAt={project.createdAt}
      subtitle={
        <>
          {project.numberReportsTotal} reports · <RelativeTime date={project.createdAt} />
        </>
      }
      steps={rowSteps}
      people={people}
      menu={menu}
    />
  );
}
