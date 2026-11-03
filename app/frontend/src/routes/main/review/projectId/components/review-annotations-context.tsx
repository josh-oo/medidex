import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { ProjectAnnotationsDto } from "@/types/apiDTOs";

interface ReviewAnnotationsContextValue {
  annotations: ProjectAnnotationsDto;
  /** A report left the review (merged or deleted): the list is loaded again. */
  reportFinished: () => void;
}

const ReviewAnnotationsContext = createContext<ReviewAnnotationsContextValue>({
  annotations: {},
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
  const value = useMemo<ReviewAnnotationsContextValue>(
    () => ({ annotations, reportFinished: onReportFinished }),
    [annotations, onReportFinished]
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
  const { reportFinished } = useContext(ReviewAnnotationsContext);
  return { reportFinished };
}
