"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import type { ProjectAnnotationsDto } from "@/types/apiDTOs";

interface ReviewAnnotationsContextValue {
  annotations: ProjectAnnotationsDto;
  updateConfirmedForReportStudy: (
    reportId: string,
    studyId: number,
    confirmed: boolean
  ) => void;
}

const ReviewAnnotationsContext = createContext<ReviewAnnotationsContextValue>({
  annotations: {},
  updateConfirmedForReportStudy: () => {},
});

interface ReviewAnnotationsProviderProps {
  annotations: ProjectAnnotationsDto;
  children: ReactNode;
}

export function ReviewAnnotationsProvider({
  annotations,
  children,
}: ReviewAnnotationsProviderProps) {
  const [annotationsState, setAnnotationsState] = useState<ProjectAnnotationsDto>(annotations);

  const value = useMemo<ReviewAnnotationsContextValue>(
    () => ({
      annotations: annotationsState,
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
    [annotationsState]
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
  const { updateConfirmedForReportStudy } = useContext(ReviewAnnotationsContext);
  return { updateConfirmedForReportStudy };
}
