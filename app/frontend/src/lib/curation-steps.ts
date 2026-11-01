// The curation of a project as a chain of steps, from the counts of its ProjectDto (or the TaskDto of an
// assignee). Preprocessing and the automatic PDF search run side by side; the PDFs the search did not find are
// uploaded by hand; a report with a PDF and an embedding goes on through the extra steps of extensions (e.g. a
// postprocessing), is linked to its study by the assignees and, once all of them have committed their links of it,
// merged into the core database (or deleted) by the owner in the review. A step can only reach as far as the steps before it let it:
// `ready` is that limit, `done` what the step has finished.
import {
  ClipboardCheck,
  Cpu,
  FileSearch,
  FileUp,
  Link2,
  type LucideIcon,
} from "lucide-react";
import type { ProjectDto, TaskDto } from "@/types/apiDTOs";

export interface CurationStep {
  key: string;
  label: string;
  icon: LucideIcon;
  /** Reports through this step. */
  done: number;
  /** Reports the steps before have made ready for this one (at least `done`). */
  ready: number;
  /** Reports of the project. */
  total: number;
  /** What the numbers mean in words: "done / ready" and what the step does, e.g. "4 / 10 uploaded". */
  detail: string;
  /** A person works on this step (the automatic ones run by themselves). */
  manual?: boolean;
  /** Steps of the same group run side by side. */
  group?: string;
  /** What a person does in this step, e.g. "Upload PDFs". */
  action?: string;
  /** Where the work of the step is done; only set when the current user may do it. */
  href?: string;
  /** Why the current user cannot do the step (shown when they click its ring). */
  hint?: string;
  /** What they can do about it, e.g. assign themselves. */
  hintAction?: { label: string; run: () => void };
}

/** What the current user may do on a project. */
export interface CurationRole {
  /** Uploaded the project: uploads the missing PDFs and reviews the links. */
  isOwner: boolean;
  /** Is assigned to it: links its reports. */
  isAssignee: boolean;
}

export const curationPaths = {
  overview: "/curation",
  projects: (projectId: string) => `/curation/projects/${encodeURIComponent(projectId)}`,
  pdfUpload: (projectId: string) => `/curation/pdf-upload/${encodeURIComponent(projectId)}`,
  review: (projectId: string) => `/curation/review/${encodeURIComponent(projectId)}`,
};

const clampCount = (value: number | undefined, max: number) =>
  Math.min(Math.max(Number.isFinite(value) ? (value as number) : 0, 0), max);

/** A step with its counts kept within the project, `ready` never below `done`. */
export const makeStep = (step: CurationStep): CurationStep => {
  const total = Math.max(step.total, 0);
  const done = clampCount(step.done, total);
  return { ...step, total, done, ready: Math.max(done, clampCount(step.ready, total)) };
};

export function projectSteps(project: ProjectDto, role: CurationRole, extraSteps: CurationStep[] = []): CurationStep[] {
  const total = project.numberReportsTotal;
  const searched = project.numberReportsAutoSearchedPdf;
  const withPdf = project.numberReportsWithPdf;
  // The linkage of a report is done once every assignee has linked it.
  const linked = project.assignees.length > 0 ? project.numberReportsReadyForReview : 0;
  const readyToLink = project.numberReportsReadyForProcessing;
  const finished = project.numberReportsMerged + project.numberReportsDeleted;

  return [
    makeStep({
      key: "preprocessing",
      label: "Preprocessing",
      icon: Cpu,
      done: project.numberReportsPreProcessed,
      ready: total,
      total,
      detail: `${project.numberReportsPreProcessed} / ${total}`,
      group: "intake",
    }),
    makeStep({
      key: "pdf-search",
      label: "PDF search",
      icon: FileSearch,
      done: searched,
      ready: total,
      total,
      detail: `${searched} / ${total} searched`,
      group: "intake",
    }),
    makeStep({
      key: "pdf-upload",
      label: "PDFs",
      icon: FileUp,
      done: withPdf,
      ready: Math.max(searched, withPdf),
      total,
      detail: `${withPdf} / ${Math.max(searched, withPdf)} uploaded`,
      manual: true,
      action: "Upload PDFs",
      href: role.isOwner ? curationPaths.pdfUpload(project.projectId) : undefined,
      hint: role.isOwner ? undefined : "Only the owner of this project uploads its missing PDFs.",
    }),
    ...extraSteps,
    makeStep({
      key: "linkage",
      label: "Linkage",
      icon: Link2,
      done: linked,
      ready: readyToLink,
      total,
      detail: `${linked} / ${Math.max(readyToLink, linked)} linked`,
      manual: true,
      action: "Link",
      href: role.isAssignee ? curationPaths.projects(project.projectId) : undefined,
      hint: role.isAssignee ? undefined : "You are not assigned to this project yet.",
    }),
    makeStep({
      key: "review",
      label: "Review",
      icon: ClipboardCheck,
      done: finished,
      // A report is merged once every assignee has committed their links of it.
      ready: project.numberReportsReadyForMerge,
      total,
      detail: `${finished} / ${Math.max(project.numberReportsReadyForMerge, finished)} merged`,
      manual: true,
      action: "Merge",
      href: role.isOwner ? curationPaths.review(project.projectId) : undefined,
      hint: role.isOwner ? undefined : "Only the owner of this update merges its links.",
    }),
  ];
}

/** The part of a project an assignee works on: linking its reports. */
export function taskSteps(task: TaskDto): CurationStep[] {
  const ready = task.numberReportsReadyForProcessing;
  return [
    makeStep({
      key: "linkage",
      label: "Your linkage",
      icon: Link2,
      done: task.numberReportsProcessed,
      ready,
      // Older backends do not send the total; the ready reports are then all there is to see.
      total: task.numberReportsTotal || ready,
      detail: `${task.numberReportsProcessed} / ${Math.max(ready, task.numberReportsProcessed)} linked`,
      manual: true,
      action: "Link",
      href: curationPaths.projects(task.projectId),
    }),
  ];
}

/** The reports of a step waiting for the current user: ready for it, not through it yet, and theirs to work on. */
export const waitingReports = (step: CurationStep) => (step.manual && step.href ? step.ready - step.done : 0);
