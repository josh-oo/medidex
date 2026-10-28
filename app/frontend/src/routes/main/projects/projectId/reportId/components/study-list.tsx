import { isNotFound } from "@/lib/api/errors";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { CandidateStudyTable } from "@/components/ui/study-view/candidate-study-table";
import { Skeleton } from "@/components/ui/skeleton";
import type { StudyCandidateDto } from "@/types/apiDTOs";
import { getReferencedStudiesByReportId, getSimilarStudiesByReportId } from "@/lib/api/reportApi";
import { ReportActionsSlot } from "@/context/study-report-slots-context";

const PAGE_SIZE = 10;

export default function StudyList() {
  const { reportId } = useParams<{ reportId: string }>() as { reportId: string };
  const reportIdNumber = Number(reportId);

  const [studies, setStudies] = useState<StudyCandidateDto[] | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [referencedStudies, setReferencedStudies] = useState<StudyCandidateDto[]>([]);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setStudies(null);
    setNextCursor(null);
    setNotFound(false);
    setLoadError(false);

    getSimilarStudiesByReportId(reportIdNumber, undefined, { params: { limit: PAGE_SIZE } })
      .then((response) => {
        if (cancelled) return;
        setStudies(response.items);
        setNextCursor(response.nextCursor);
      })
      .catch((error) => {
        if (cancelled) return;
        if (isNotFound(error)) {
          setNotFound(true);
        } else {
          console.error(`Error fetching similar studies for report ${reportIdNumber}:`, error);
          setLoadError(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [reportIdNumber]);

  // Secondary, best-effort section - a failure here just leaves it hidden rather than
  // blocking the similar studies.
  useEffect(() => {
    let cancelled = false;
    setReferencedStudies([]);

    getReferencedStudiesByReportId(reportIdNumber)
      .then((response) => {
        if (!cancelled) setReferencedStudies(response);
      })
      .catch(() => {});

    return () => {
      cancelled = true;
    };
  }, [reportIdNumber]);

  const handleLoadMore = () => {
    if (!nextCursor || isLoadingMore) return;

    setIsLoadingMore(true);
    getSimilarStudiesByReportId(reportIdNumber, undefined, {
      params: { limit: PAGE_SIZE, cursor: nextCursor },
    })
      .then((response) => {
        setStudies((prev) => [...(prev ?? []), ...response.items]);
        setNextCursor(response.nextCursor);
      })
      .catch((error) => {
        console.error(`Error loading more studies for report ${reportIdNumber}:`, error);
        toast.error("Failed to load more studies");
      })
      .finally(() => {
        setIsLoadingMore(false);
      });
  };

  if (notFound) {
    return (
      <div className="flex min-h-[40vh] w-full items-center justify-center text-sm text-muted-foreground">
        Report not found.
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex min-h-[40vh] w-full items-center justify-center text-sm text-muted-foreground">
        Failed to load studies for this report.
      </div>
    );
  }

  if (studies === null) {
    return <StudyListSkeleton />;
  }

  return (
    <>
      <CandidateStudyTable
        reportId={reportIdNumber}
        studies={studies}
        referencedStudies={referencedStudies}
        nextCursor={nextCursor}
        isLoadingMore={isLoadingMore}
        onLoadMore={handleLoadMore}
      />
      <ReportActionsSlot reportId={reportIdNumber} studies={studies} />
    </>
  );
}

export function StudyListSkeleton() {
  const rowPlaceholders = Array.from({ length: 5 });

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border bg-card p-5 space-y-3">
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-9 w-full rounded-md" />
      </div>
      <div className="rounded-2xl border bg-card p-5 space-y-2">
        <Skeleton className="h-5 w-36 mb-2" />
        {rowPlaceholders.map((_, index) => (
          <div key={index} className="flex items-center gap-3 rounded-xl bg-muted/60 p-3">
            <Skeleton className="h-10 w-10 rounded-full shrink-0" />
            <div className="flex-1 min-w-0 space-y-2">
              <Skeleton className="h-4 w-2/5" />
              <Skeleton className="h-3 w-4/5" />
            </div>
            <Skeleton className="h-8 w-24 rounded-full shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}
