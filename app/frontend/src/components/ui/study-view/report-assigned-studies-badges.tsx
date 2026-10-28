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

import { isNewStudyAssignment } from "@/lib/study-assignment";
import { cn } from "@/lib/utils";
import { Loader2, X } from "lucide-react";
import React, { useState } from "react";

import type { StudyPreviewDto, ReportDto, ReportCurationDto} from "../../../types/apiDTOs";

import { toast } from "sonner";

import { useReportStore } from "@/hooks/use-report-store";
import { useDetailsSheet } from "@/context/details-sheet-context";

interface ReportAssignedStudiesBadgesProps {
  report: ReportCurationDto;
}

export function ReportAssignedStudiesBadges({
  report,
}: ReportAssignedStudiesBadgesProps) {

  // All hooks must be called unconditionally, before any return
  const removeAssignedStudy = useReportStore((state) => state.removeAssignedStudy);
  const reportInStore = useReportStore((state) => state.reports[report.reportId]);
  const assignedStudies = reportInStore?.assignedStudies ?? report.assignedStudies;
  const [removingAssignments, setRemovingAssignments] = useState<Set<string>>(new Set());
  const [removing, setRemoving] = useState<Set<string>>(new Set());
  const [studyToRemove, setStudyToRemove] = useState<{
    report: ReportDto;
    study: StudyPreviewDto;
  } | null>(null);
  const getAssignmentKey = (reportId: number, studyId: number) => `${reportId}-${studyId}`;
  const isRemovalDialogOpen = Boolean(studyToRemove);
  const isConfirmingRemoval = studyToRemove
    ? removingAssignments.has(getAssignmentKey(studyToRemove.report.reportId, studyToRemove.study.studyId))
    : false;
  const { openWithStudyId } = useDetailsSheet();

  if (!assignedStudies || assignedStudies.length == 0){
    return null;
  }

  // Handle badge click
  const handleStudyBadgeClick = (event: React.MouseEvent, studyId: number) => {
    event.stopPropagation();
    event.preventDefault();
    openWithStudyId(studyId);
  };

  // Open dialog for confirmation instead of removing directly
  const onRemoveAssignedStudy = async (report : ReportDto, study : StudyPreviewDto) => {
        if (report && study) {
            setStudyToRemove({ report: report, study: study });
        }
  };

  const handleConfirmRemove = async () => {
    if (!studyToRemove) {
      return;
    }
    const { report, study } = studyToRemove;
    setRemovingAssignments((prev) => new Set(prev).add(`${report.reportId}-${study.studyId}`));
    try {
      await removeAssignedStudy(report.reportId, study.studyId);
      toast.success(`Removed study ${study.shortName} from report`);
      setStudyToRemove(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      toast.error(`Failed to remove study ${study.shortName}: ${message}`);
    } finally {
      setRemovingAssignments((prev) => {
        const next = new Set(prev);
        next.delete(`${report.reportId}-${study.studyId}`);
        return next;
      });
    }
  };

  // Handle remove click
  const handleRemoveClick = async (
    event: React.MouseEvent,
    report: ReportDto,
    study: StudyPreviewDto
  ) => {
    event.stopPropagation();
    event.preventDefault();
    const assignmentKey = getAssignmentKey(report.reportId, study.studyId);
    setRemoving((prev) => new Set(prev).add(assignmentKey));
    try {
      await onRemoveAssignedStudy(report, study);
    } finally {
      setRemoving((prev) => {
        const next = new Set(prev);
        next.delete(assignmentKey);
        return next;
      });
    }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <span className="mr-0.5 text-xs text-muted-foreground">Linked to</span>
      {assignedStudies.map((study) => {
        const assignmentKey = getAssignmentKey(report.reportId, study.studyId);
        // Use local removing state in addition to parent removingAssignments
        const isRemovingAssignment = removingAssignments.has(assignmentKey) || removing.has(assignmentKey);
        // The same colours as the dots of the report list: blue for a new study, green for an existing one.
        const isNewStudy = isNewStudyAssignment(
          study.createdAt,
          report.createdAt
        );
        return (
          <span
            key={study.studyId}
            className={cn(
              "group inline-flex items-center gap-1 rounded-full py-0.5 pl-2.5 pr-1 text-xs font-medium",
              isNewStudy
                ? "bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300"
                : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"
            )}
          >
            <button
              type="button"
              className="cursor-pointer hover:underline"
              title={isNewStudy ? "New study, created for this report" : "Existing study"}
              onClick={(event) => handleStudyBadgeClick(event, study.studyId)}
            >
              {study.shortName}
            </button>
            {isNewStudy && <span className="text-[10px] font-normal opacity-70">new</span>}
            <button
              type="button"
              className="inline-flex h-4 w-4 items-center justify-center rounded-full opacity-60 hover:bg-black/5 hover:opacity-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-60 dark:hover:bg-white/10"
              title="Remove study from report"
              aria-label={`Remove study ${study.shortName} from report`}
              onClick={(event) => {
                event.stopPropagation();
                event.preventDefault();
                handleRemoveClick(event, report, study);
              }}
              disabled={isRemovingAssignment}
            >
              {isRemovingAssignment ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <X className="h-3 w-3" />
              )}
            </button>
          </span>
        );
      })}
      {studyToRemove && (
        <AlertDialog
          open={isRemovalDialogOpen}
          onOpenChange={(open) => {
            if (!open) {
              setStudyToRemove(null);
            }
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Remove study assignment?</AlertDialogTitle>
              <AlertDialogDescription>
                <span>
                  This will remove report <strong>{studyToRemove.report.title}</strong> from study <strong>{studyToRemove.study.shortName}</strong>.
                </span>
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel disabled={isConfirmingRemoval}>
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction onClick={handleConfirmRemove} disabled={isConfirmingRemoval}>
                {isConfirmingRemoval && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Remove
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      )}
    </div>
  );
}