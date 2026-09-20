"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Search, Calendar, UserPlus, Check, Settings, FileUp, ClipboardCheck, Trash2, Bot, ArrowDown, Microscope, AlertTriangle } from "lucide-react";
import RelativeTime from "@/components/ui/relative-time";
import type { ProjectDetailsDto, ProjectAssigneeDto } from "@/types/apiDTOs";
import type { UserDto } from "@/types/user/user.dto";

const EMPTY_USERS: UserDto[] = [];
const MEDIBOT_USER: UserDto = {
  id: "bot",
  name: "MediBot",
  email: "",
  roles: [],
  isApproved: true,
};

const withMediBot = (users: UserDto[]) => {
  const hasMediBot = users.some((user) => user.id === MEDIBOT_USER.id);
  return hasMediBot ? users : [...users, MEDIBOT_USER];
};

interface ProjectCardProps {
  project: ProjectDetailsDto;
  index?: number;
  assignableUsers?: UserDto[];
  onAssigneesChange?: (payload: { projectId: string; userIds: string[] }) => void;
}

const getUserInitials = (name?: string) => {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/).slice(0, 2);
  return parts
    .map((part) => part.charAt(0).toUpperCase())
    .join("")
    .slice(0, 2);
};

const clamp = (value: number, min = 0, max = 100) => {
  if (Number.isNaN(value)) return min;
  return Math.min(Math.max(value, min), max);
};

export function ProjectCard({
  project,
  index = 0,
  assignableUsers = EMPTY_USERS,
  onAssigneesChange,
}: ProjectCardProps) {
  const router = useRouter();
  const refreshTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [assigneeIds, setAssigneeIds] = useState<string[]>(() =>
    (project.assignees ?? []).map((assignee) => assignee.userId),
  );
  const [isAssigneePopoverOpen, setIsAssigneePopoverOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [pendingAssigneeId, setPendingAssigneeId] = useState<string | null>(null);
  const availableUsers = useMemo(() => withMediBot(assignableUsers), [assignableUsers]);
  const isUpdatingAssignees = pendingAssigneeId !== null;

  useEffect(() => {
    setAssigneeIds((project.assignees ?? []).map((assignee) => assignee.userId));
  }, [project.assignees]);

  useEffect(() => {
    const streamUrl = `/api/meerkat/projects/${encodeURIComponent(project.projectId)}/stream`;
    const eventSource = new EventSource(streamUrl);

    const handleMessage = (event: MessageEvent) => {
      console.log(`Project update received for ${project.projectId}:`, event.data);

      if (refreshTimeoutRef.current !== null) {
        clearTimeout(refreshTimeoutRef.current);
      }

      refreshTimeoutRef.current = setTimeout(() => {
        refreshTimeoutRef.current = null;
        router.refresh();
      }, 200);
    };

    const handleError = (event: Event) => {
      console.error(`Project stream error for ${project.projectId}:`, event);
    };

    eventSource.addEventListener("message", handleMessage);
    eventSource.addEventListener("error", handleError);

    return () => {
      if (refreshTimeoutRef.current !== null) {
        clearTimeout(refreshTimeoutRef.current);
        refreshTimeoutRef.current = null;
      }
      eventSource.removeEventListener("message", handleMessage);
      eventSource.removeEventListener("error", handleError);
      eventSource.close();
    };
  }, [project.projectId, router]);

  const sortedUsers = useMemo(
    () => [...availableUsers].sort((a, b) => a.email.localeCompare(b.email)),
    [availableUsers],
  );

  const knownUsers = useMemo(() => {
    const map = new Map<string, UserDto>();
    sortedUsers.forEach((user) => map.set(user.id, user));
    return map;
  }, [sortedUsers]);

  const automationUsers = useMemo(
    () => sortedUsers.filter((user) => user.id === MEDIBOT_USER.id),
    [sortedUsers]
  );
  const humanUsers = useMemo(
    () => sortedUsers.filter((user) => user.id !== MEDIBOT_USER.id),
    [sortedUsers]
  );

  const assigneeMap = useMemo(() => {
    const map = new Map<string, ProjectAssigneeDto>();
    (project.assignees ?? []).forEach((assignee) => map.set(assignee.userId, assignee));
    return map;
  }, [project.assignees]);

  const resolvedAssignees = assigneeIds.map((userId) => ({
    userId,
    profile: knownUsers.get(userId),
  }));

  const hasAssignees = assigneeIds.length > 0;

  const toggleAssignee = useCallback(
    async (userId: string) => {
      if (isUpdatingAssignees) {
        return;
      }
      const normalizedUserId = userId.trim();
      if (!normalizedUserId) {
        return;
      }
      const isSelected = assigneeIds.includes(normalizedUserId);
      const endpoint = isSelected
        ? `/api/meerkat/projects/${project.projectId}/assignees/${encodeURIComponent(normalizedUserId)}`
        : `/api/meerkat/projects/${project.projectId}/assignees`;
      const requestInit: RequestInit = isSelected
        ? { method: "DELETE" }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(normalizedUserId),
          };

      setPendingAssigneeId(normalizedUserId);
      try {
        const response = await fetch(endpoint, requestInit);
        if (!response.ok) {
          let detail = "Failed to update project assignees.";
          const bodyText = await response.text();
          if (bodyText) {
            try {
              const data = JSON.parse(bodyText);
              if (typeof data?.detail === "string") {
                detail = data.detail;
              } else {
                detail = bodyText;
              }
            } catch {
              detail = bodyText;
            }
          }
          throw new Error(detail);
        }

        setAssigneeIds((prev) => {
          const next = isSelected
            ? prev.filter((id) => id !== normalizedUserId)
            : [...prev, normalizedUserId];
          onAssigneesChange?.({ projectId: project.projectId, userIds: next });
          return next;
        });
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
    [assigneeIds, isUpdatingAssignees, onAssigneesChange, project.projectId]
  );

  const handleDeleteProject = useCallback(async () => {
    if (isDeleting) return;

    setIsDeleting(true);
    try {
      const response = await fetch(`/api/meerkat/projects/${project.projectId}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "Failed to delete project");
      }

      setIsDeleteDialogOpen(false);
      router.refresh();
    } catch (error) {
      console.error("Failed to delete project", error);
      window.alert("Unable to delete project. Please try again or contact an administrator.");
    } finally {
      setIsDeleting(false);
    }
  }, [isDeleting, project.name, project.projectId, router]);

  const totalReports = project.numberReportsTotal;
  const preprocessedCount = project.numberReportsPreProcessed;
  const hasPdfCount = project.numberReportsWithPdf
  const readyForProcessingCount = project.numberReportsReadyForProcessing;
  const readyForManualPdfSearch = project.numberReportsAutoSearchedPdf;
  const readyForReviewCount = project.numberReportsReadyForReview;
  const readyConfirmedCount = project.numberReportsConfirmed;

  const handleStartPdfUpload = useCallback(() => {
    const path = `/pdf-upload/${encodeURIComponent(project.projectId)}`;
    router.push(path);
  }, [project.projectId, router]);

  const handleStartReview = useCallback(() => {
    const path = `/review/${encodeURIComponent(project.projectId)}`;
    router.push(path);
  }, [project.projectId, router]);


  const processingStage = {
    label: "Preprocessing",
    icon: Settings,
    value: preprocessedCount,
    total: totalReports,
    fillClass: "bg-primary/60",
  };

  const pdfAutoSearchStage = {
    label: "PDF Search",
    icon: Search,
    value: readyForManualPdfSearch,
    total: totalReports,
    fillClass: "bg-primary/60",
  };

  const pdfStage = {
    label: "Upload Missing PDFs",
    icon: FileUp,
    value: hasPdfCount,
    total: readyForManualPdfSearch,
    fillClass: "bg-primary",
    onClick: handleStartPdfUpload,
  };

  const reviewStage = {
    label: "Review results",
    icon: ClipboardCheck,
    value: readyConfirmedCount,
    total: readyForReviewCount,
    fillClass: "bg-emerald-500/70",
    onClick: handleStartReview,
  };

  const processingStagePercent = processingStage && processingStage.total > 0
    ? Math.round((processingStage.value / processingStage.total) * 100)
    : 0;

  const pdfSerchPercent = pdfAutoSearchStage && pdfAutoSearchStage .total > 0
    ? Math.round((pdfAutoSearchStage .value / pdfAutoSearchStage .total) * 100)
    : 0;

  const getReviewerProgress = (userId: string) =>
    clamp(((assigneeMap.get(userId)?.numberReportsLinked ?? 0) / totalReports) * 100);

  const assigneeProgressPanels = resolvedAssignees.map(({ userId, profile }) => {
    const linkedReports = assigneeMap.get(userId)?.numberReportsLinked ?? 0;
    return {
      userId,
      name: profile?.name ?? userId,
      percent: getReviewerProgress(userId),
      linkedReports,
    };
  });
  const orderedAssigneePanels = assigneeProgressPanels.length
    ? [
        ...assigneeProgressPanels.filter((panel) => panel.userId === MEDIBOT_USER.id),
        ...assigneeProgressPanels.filter((panel) => panel.userId !== MEDIBOT_USER.id),
      ]
    : assigneeProgressPanels;
  const hasAssigneePanels = orderedAssigneePanels.length > 0;
  const isSingleAssigneePanel = orderedAssigneePanels.length === 1;

  const renderUserCommandItem = (user: UserDto) => {
    const isSelected = assigneeIds.includes(user.id);
    const isMediBotUser = user.id === MEDIBOT_USER.id;
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
            {isMediBotUser ? <Bot className="h-3.5 w-3.5" aria-hidden /> : getUserInitials(user.name)}
          </AvatarFallback>
        </Avatar>
        <div className="flex-1 truncate">
          <p className="text-sm font-medium leading-tight truncate">{user.name}</p>
        </div>
        {isSelected && <Check className="h-4 w-4 text-primary" />}
      </CommandItem>
    );
  };

  return (
    <div
      className="group relative text-left bg-card border p-5 transition-all hover:border-primary/40 hover:shadow-md"
      style={{ animationDelay: `${index * 50}ms` }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-base group-hover:text-primary transition-colors line-clamp-2 leading-snug">
            {project.name}
          </h3>
          <p className="text-xs text-muted-foreground mt-1.5 flex items-center gap-1.5">
            <Calendar className="w-3 h-3" />
            <RelativeTime date={project.createdAt} />
          </p>
        </div>
        <AlertDialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
          <AlertDialogTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={(event) => {
                event.stopPropagation();
              }}
              disabled={isDeleting}
            >
              <Trash2 className="w-4 h-4 text-destructive" />
              <span className="sr-only">Delete project</span>
            </Button>
          </AlertDialogTrigger>
          <AlertDialogContent
            className="sm:max-w-md"
            onClick={(event) => event.stopPropagation()}
          >
            <AlertDialogHeader>
              <div className="mb-2 flex items-center gap-2 text-destructive">
                <AlertTriangle className="h-4 w-4" aria-hidden />
                <span className="text-xs font-semibold uppercase tracking-wide">Danger Zone</span>
              </div>
              <AlertDialogTitle>Delete project?</AlertDialogTitle>
              <AlertDialogDescription>
                This will permanently remove all data for this project.
              </AlertDialogDescription>
              <div className="mt-2 rounded-md border border-border/70 bg-muted/30 px-3 py-2 text-sm text-foreground">
                {project.name}
              </div>
            </AlertDialogHeader>
            <AlertDialogFooter className="gap-2 sm:gap-2">
              <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleDeleteProject}
                disabled={isDeleting}
                className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              >
                {isDeleting ? "Deleting..." : "Delete project"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>

      <div className="mt-4 space-y-3">
        {processingStage && processingStage.icon && (
          <div className="rounded-md border border-dashed border-border/60 bg-muted/20 px-3 py-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
              <div className="flex items-center gap-1 font-semibold uppercase tracking-wide">
                {processingStage.icon && <processingStage.icon className="h-3.5 w-3.5" />}
                <span>{processingStage.label}</span>
              </div>
              <span className="text-sm font-semibold text-muted-foreground">
                {processingStage.value} / {processingStage.total}
              </span>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full ${processingStage.fillClass}`}
                style={{ width: `${processingStagePercent}%` }}
              />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground pt-4">
              <div className="flex items-center gap-1 font-semibold uppercase tracking-wide">
                {pdfAutoSearchStage.icon && <pdfAutoSearchStage.icon className="h-3.5 w-3.5" />}
                <span>{pdfAutoSearchStage.label}</span>
              </div>
              <span className="text-sm font-semibold text-muted-foreground">
                {pdfAutoSearchStage.value} / {pdfAutoSearchStage.total}
              </span>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full ${pdfAutoSearchStage.fillClass}`}
                style={{ width: `${pdfSerchPercent}%` }}
              />
            </div>
          </div>
        )}

        <div className="flex justify-center py-0.5 text-muted-foreground/70" aria-hidden>
          <ArrowDown className="h-4 w-4" />
        </div>

        {pdfStage && pdfStage.icon && (
          <button
            type="button"
            className="w-full rounded-md border border-dashed border-border/60 bg-muted/20 px-3 py-2 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
            onClick={(event) => {
              event.stopPropagation();
              pdfStage.onClick?.();
            }}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-foreground">
              <div className="flex items-center gap-1 font-semibold uppercase tracking-wide">
                {pdfStage.icon && <pdfStage.icon className="h-3.5 w-3.5" />}
                <span>{pdfStage.label}</span>
              </div>
              <span className="text-sm font-semibold text-foreground">
                {pdfStage.value} / {pdfStage.total}
              </span>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full ${pdfStage.fillClass}`}
                style={{ width: `${pdfStage.total > 0 ? Math.round((pdfStage.value / pdfStage.total) * 100) : 0}%` }}
              />
            </div>
          </button>
        )}

        <div className="flex justify-center py-0.5 text-muted-foreground/70" aria-hidden>
          <ArrowDown className="h-4 w-4" />
        </div>

        <div className="rounded-md border border-dashed border-border/60 bg-muted/20 px-3 py-2">
          <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-1 font-semibold uppercase tracking-wide">
              <Microscope className="h-3.5 w-3.5" aria-hidden />
              <span>Studification</span>
            </div>
          </div>

          <div
            className={`mt-2 flex w-full gap-3 overflow-x-auto pb-1 snap-x snap-mandatory items-stretch ${
              isSingleAssigneePanel ? "justify-center" : "justify-start"
            }`}
          >
            {hasAssigneePanels ? (
              orderedAssigneePanels.map((panel) => {
                const isMediBot = panel.userId === MEDIBOT_USER.id;
                
                return (
                  <div
                    key={panel.userId}
                    className="min-w-[15rem] rounded-md border border-border/60 bg-background/80 px-3 py-2 text-left flex flex-col justify-between h-full snap-start"
                  >
                    <div className="flex items-center justify-between gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      <span className="truncate flex items-center gap-1.5">
                        {isMediBot && <Bot className="h-3.5 w-3.5" aria-hidden />}
                        <span className="truncate">{panel.name}</span>
                      </span>
                        <span className="shrink-0 text-foreground">
                          {panel.linkedReports} / {readyForProcessingCount}
                        </span>
                    </div>
                    <div className="mt-1.5 h-1.5 rounded-full bg-muted overflow-hidden">
                      <div className="h-full rounded-full bg-primary/60" style={{ width: `${panel.percent}%` }} />
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="flex-1 min-w-full flex-shrink-0 rounded-md border border-dashed border-border/60 bg-muted/30 px-3 py-2 text-xs text-muted-foreground flex items-center justify-center text-center h-full">
                Assign at least one studificator to start tracking progress.
              </div>
            )}
          </div>
        </div>

        <div className="flex justify-center py-0.5 text-muted-foreground/70" aria-hidden>
          <ArrowDown className="h-4 w-4" />
        </div>

        {reviewStage && reviewStage.icon && (
          <button
            type="button"
            className="w-full rounded-md border border-dashed border-border/60 bg-muted/20 px-3 py-2 text-left transition-colors hover:border-primary/40 hover:bg-muted/30"
            onClick={(event) => {
              event.stopPropagation();
              reviewStage.onClick?.();
            }}
          >
            <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-foreground">
              <div className="flex items-center gap-1 font-semibold uppercase tracking-wide">
                {reviewStage.icon && <reviewStage.icon className="h-3.5 w-3.5" />}
                <span>{reviewStage.label}</span>
              </div>
              <span className="text-sm font-semibold text-foreground">
                {reviewStage.value} / {reviewStage.total}
              </span>
            </div>
            <div className="mt-2 h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full ${reviewStage.fillClass}`}
                style={{ width: `${reviewStage.total > 0 ? Math.round((reviewStage.value / reviewStage.total) * 100) : 0}%` }}
              />
            </div>
          </button>
        )}
      </div>

      <div className="mt-4 space-y-3 border-t border-border/50 pt-3">
        <div className="flex items-center gap-2">
          <div className="flex flex-1 items-center min-h-10">
            {hasAssignees ? (
              <p className="text-xs text-muted-foreground">
                {resolvedAssignees.length} studificator{resolvedAssignees.length === 1 ? "" : "s"} assigned.
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">No studificators assigned yet.</p>
            )}
          </div>
          <Popover open={isAssigneePopoverOpen} onOpenChange={setIsAssigneePopoverOpen}>
            <PopoverTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="ml-auto h-8 w-8"
                onClick={(event) => event.stopPropagation()}
              >
                <UserPlus className="h-4 w-4" />
                <span className="sr-only">Assign reviewers</span>
              </Button>
            </PopoverTrigger>
            <PopoverContent
              className="w-64 p-0"
              align="end"
              sideOffset={8}
              onClick={(event) => event.stopPropagation()}
              onKeyDown={(event) => event.stopPropagation()}
            >
              <Command>
                <CommandInput placeholder="Search users..." />
                <CommandList className="max-h-64 overflow-y-auto">
                  <CommandEmpty>No users found.</CommandEmpty>
                  {sortedUsers.length ? (
                    <>
                      {automationUsers.length > 0 && (
                        <CommandGroup heading="Automation">
                          {automationUsers.map(renderUserCommandItem)}
                        </CommandGroup>
                      )}
                      {humanUsers.length > 0 && (
                        <CommandGroup heading="Team">
                          {humanUsers.map(renderUserCommandItem)}
                        </CommandGroup>
                      )}
                    </>
                  ) : (
                    <div className="px-3 py-6 text-center text-sm text-muted-foreground">
                      No reviewers available yet.
                    </div>
                  )}
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>
  );
}
