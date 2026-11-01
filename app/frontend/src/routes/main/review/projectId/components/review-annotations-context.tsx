import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { ProjectAnnotationsDto } from "@/types/apiDTOs";

interface ReviewAnnotationsContextValue {
  annotations: ProjectAnnotationsDto;
  updateConfirmedForReportStudy: (
    reportId: string,
    studyId: number,
    confirmed: boolean
  ) => void;
  /** A report left the review (merged or deleted): the list is loaded again. */
  reportFinished: () => void;
}

const ReviewAnnotationsContext = createContext<ReviewAnnotationsContextValue>({
  annotations: {},
  updateConfirmedForReportStudy: () => {},
  reportFinished: () => {},
});

interface ReviewAnnotationsProviderProps {
  annotations: ProjectAnnotationsDto;
  onReportFinished: () => void;
  children: ReactNode;
}

export function ReviewAnnotationsProvider({
  annotations,
  onReportFinished,
  children,
}: ReviewAnnotationsProviderProps) {
  const [annotationsState, setAnnotationsState] = useState<ProjectAnnotationsDto>(annotations);

  const value = useMemo<ReviewAnnotationsContextValue>(
    () => ({
      annotations: annotationsState,
      reportFinished: onReportFinished,
      updateConfirmedForReportStudy: (reportId, studyId, confirmed) => {
        setAnnotationsState((prev) => {
          const reportAnnotations = prev[reportId];
          if (!reportAnnotations || reportAnnotations.studies.length === 0) {
            return prev;
          }

          let hasChanges = false;
          const nextStudyAnnotations = reportAnnotations.studies.map((annotation) => {
            if (annotation.studyId !== studyId || annotation.confirmed === confirmed) {
              return annotation;
            }
            hasChanges = true;
            return {
              ...annotation,
              confirmed,
            };
          });

          if (!hasChanges) {
            return prev;
          }

          return {
            ...prev,
            [reportId]: {
              ...reportAnnotations,
              studies: nextStudyAnnotations,
            },
          };
        });
      },
    }),
    [annotationsState, onReportFinished]
  );

  return (
    <ReviewAnnotationsContext.Provider value={value}>
      {children}
    </ReviewAnnotationsContext.Provider>
  );
}

export function useReviewAnnotations(): ProjectAnnotationsDto {
  return useContext(ReviewAnnotationsContext).annotations;
}

export function useReviewAnnotationsActions() {
  const { updateConfirmedForReportStudy, reportFinished } = useContext(ReviewAnnotationsContext);
  return { updateConfirmedForReportStudy, reportFinished };
}
