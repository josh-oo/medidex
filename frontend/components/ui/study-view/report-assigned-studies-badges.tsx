"use client"

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

import { Badge } from "@/components/ui/badge";
import { Loader2, X } from "lucide-react";
import React, { useState } from "react";

import type { StudyDto, ReportDto, ReportDetailDto} from "../../../types/apiDTOs";

import { toast } from "sonner";

import { useReportStore } from "@/hooks/use-report-store";
import { useDetailsSheet } from "@/app/context/details-sheet-context";

interface ReportAssignedStudiesBadgesProps {
  report: ReportDetailDto;
}

export function ReportAssignedStudiesBadges({
  report,
}: ReportAssignedStudiesBadgesProps) {

  // All hooks must be called unconditionally, before any return
  const removeAssignedStudy = useReportStore((state) => state.removeAssignedStudy);
  const reportInStore = useReportStore((state) => state.reports[report.report.reportId]);
  const assignedStudies = reportInStore?.assignedStudies ?? report.assignedStudies;
  const [removingAssignments, setRemovingAssignments] = useState<Set<string>>(new Set());
  const [removing, setRemoving] = useState<Set<string>>(new Set());
  const [studyToRemove, setStudyToRemove] = useState<{
    report: ReportDto;
    study: StudyDto;
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

  // Utility: toTimestamp
  const toTimestamp = (value: Date | string | number | null | undefined): number | null => {
    if (value === null || value === undefined) {
      return null;
    }
    const date = value instanceof Date ? value : new Date(value);
    const timestamp = date.getTime();
    return Number.isFinite(timestamp) ? timestamp : null;
  };

  // Utility: isNewStudyAssignment
  const isNewStudyAssignment = (
    studyCreatedAt: Date | string | number | null | undefined,
    reportCreatedAt: Date | string | number | null | undefined
  ) => {
    const studyTimestamp = toTimestamp(studyCreatedAt);
    const reportTimestamp = toTimestamp(reportCreatedAt);
    return studyTimestamp !== null && reportTimestamp !== null && studyTimestamp > reportTimestamp;
  };

  // Handle badge click
  const handleStudyBadgeClick = (event: React.MouseEvent, studyId: number) => {
    event.stopPropagation();
    event.preventDefault();
    openWithStudyId(studyId);
  };

  // Open dialog for confirmation instead of removing directly
  const onRemoveAssignedStudy = async (report : ReportDto, study : StudyDto) => {
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
    study: StudyDto
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
    <div className="flex flex-wrap gap-1 mt-4">
      {assignedStudies.map((study) => {
        const assignmentKey = getAssignmentKey(report.report.reportId, study.studyId);
        // Use local removing state in addition to parent removingAssignments
        const isRemovingAssignment = removingAssignments.has(assignmentKey) || removing.has(assignmentKey);
        const isNewStudy = isNewStudyAssignment(
          study.createdAt,
          report.report.createdAt
        );
        return (
          <Badge
            key={study.studyId}
            variant={isNewStudy ? "destructive" : "outline"}
            className={`text-xs font-mono cursor-pointer inline-flex items-center gap-1 pr-2 ${
              isNewStudy ? "" : "border-destructive text-destructive"
            }`}
            onClick={(event) => handleStudyBadgeClick(event, study.studyId)}
          >
            <span>{study.shortName}</span>
            <button
              type="button"
              tabIndex={-1}
              className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-destructive/70 text-destructive-foreground hover:bg-destructive focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-60"
              title="Remove study from report"
              aria-label={`Remove study ${study.shortName} from report`}
              onClick={(event) => {
                event.stopPropagation();
                event.preventDefault();
                handleRemoveClick(event, report.report, study);
              }}
              disabled={isRemovingAssignment}
            >
              {isRemovingAssignment ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <X className="h-3 w-3" />
              )}
            </button>
          </Badge>
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