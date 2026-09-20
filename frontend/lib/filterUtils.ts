import { AnnotationDto, ProjectAnnotationsDto, ReportDetailDto } from "@/types/apiDTOs";

export type ReportFilterType = "all" | "assigned" | "unassigned" | "newStudy" | "withPdf" | "withoutPdf" | "flagged" | "annotatorConsensus" | "annotatorConflict" | "annotationsReview" | "annotationsNoReview";

const toTimestamp = (value: Date | string | number | null | undefined): number | null => {
  if (value === null || value === undefined) {
    return null;
  }
  const date = value instanceof Date ? value : new Date(value);
  const timestamp = date.getTime();
  return Number.isFinite(timestamp) ? timestamp : null;
};

const isNewStudyAssignment = (
  studyCreatedAt: Date | string | number | null | undefined,
  reportCreatedAt: Date | string | number | null | undefined
) => {
  const studyTimestamp = toTimestamp(studyCreatedAt);
  const reportTimestamp = toTimestamp(reportCreatedAt);
  return studyTimestamp !== null && reportTimestamp !== null && studyTimestamp > reportTimestamp;
};

// Fallback type for StudyDto if not imported
type StudyDto = { createdAt: Date | string | number | null | undefined };

const getReportAnnotations = (
  annotations: ProjectAnnotationsDto | null,
  reportId: number
): AnnotationDto[] => {
  return annotations?.[String(reportId)]?.studies ?? [];
};

const getDistinctAnnotatedStudyCount = (annotations: AnnotationDto[]): number => {
  return new Set(annotations.map((annotation) => annotation.studyId)).size;
};

const hasAnnotatorConsensus = (annotations: AnnotationDto[]): boolean => {
  if (annotations.length < 2) {
    return true;
  }

  return getDistinctAnnotatedStudyCount(annotations) === 1;
};

const hasAnnotatorConflict = (annotations: AnnotationDto[]): boolean => {
  if (annotations.length < 2) {
    return false;
  }

  return getDistinctAnnotatedStudyCount(annotations) > 1;
};

const hasReviewedAnnotation = (annotations: AnnotationDto[]): boolean => {
  return annotations.some((annotation) => annotation.confirmed);
};

export function filterReports(
  reports: ReportDetailDto[],
  annotations: ProjectAnnotationsDto|null,
  searchQuery: string,
  assignmentFilter: ReportFilterType
): ReportDetailDto[] {
  return reports.filter((report) => {
    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase();
      const matchesSearch =
        report.report.title.toLowerCase().includes(query) ||
        report.report.abstract?.toLowerCase().includes(query) ||
        report.report.reportId.toString().includes(query);
      if (!matchesSearch) return false;
    }

    // Assignment filter
    if (assignmentFilter === "assigned") {
      return report.assignedStudies.length > 0;
    }
    if (assignmentFilter === "unassigned") {
      return report.assignedStudies.length == 0;
    }
    if (assignmentFilter === "withPdf") {
      return report.hasPdf ?? false; 
    }
    if (assignmentFilter === "withoutPdf") {
      return (report.hasPdf ?? false) == false;
    }
    if (assignmentFilter === "flagged") {
      return Boolean(report.flag?.trim());
    }
    if (assignmentFilter === "newStudy") {
      return report.assignedStudies.some((study: StudyDto) =>
        isNewStudyAssignment(study.createdAt, report.report.createdAt)
      );
    }
    if (assignmentFilter === "annotatorConsensus") {
      const reportAnnotations = getReportAnnotations(annotations, report.report.reportId);
      return hasAnnotatorConsensus(reportAnnotations);
    }
    if (assignmentFilter === "annotatorConflict") {
      const reportAnnotations = getReportAnnotations(annotations, report.report.reportId);
      return hasAnnotatorConflict(reportAnnotations);
    }

    if (assignmentFilter === "annotationsReview") {
      const reportAnnotations = getReportAnnotations(annotations, report.report.reportId);
      return hasReviewedAnnotation(reportAnnotations);
    }

    if (assignmentFilter === "annotationsNoReview") {
      const reportAnnotations = getReportAnnotations(annotations, report.report.reportId);
      return !hasReviewedAnnotation(reportAnnotations);
    }

    return true;
  });
}
