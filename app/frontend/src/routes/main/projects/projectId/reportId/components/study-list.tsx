import { isNotFound } from "@/lib/api/errors";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import { CandidateStudyTable } from "@/components/ui/study-view/candidate-study-table";
import { STUDY_ROWS_PER_PAGE, StudyColumnSkeleton } from "@/components/reports/workbench-skeleton";
import { cn } from "@/lib/utils";
import type { StudyCandidateDto } from "@/types/apiDTOs";
import { getReferencedStudiesByReportId, getSimilarStudiesByReportId } from "@/lib/api/reportApi";
import { ReportActionsSlot } from "@/context/study-report-slots-context";

// A page of the list, as many as its skeleton shows.
const PAGE_SIZE = STUDY_ROWS_PER_PAGE;

// The studies of one report: the similar ones (a page of them so far) and those its references point to.
interface ReportStudies {
  reportId: number;
  studies: StudyCandidateDto[];
  nextCursor: string | null;
  referencedStudies: StudyCandidateDto[];
}

export default function StudyList() {
  const { reportId } = useParams<{ reportId: string }>() as { reportId: string };
  const reportIdNumber = Number(reportId);

  // Kept while the next report's studies load, so that the column keeps its size rather than collapsing to the
  // skeleton and growing back with every report paged to.
  const [loaded, setLoaded] = useState<ReportStudies | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setNotFound(false);
    setLoadError(false);

    Promise.all([
      getSimilarStudiesByReportId(reportIdNumber, undefined, { params: { limit: PAGE_SIZE } }),
      // Secondary, best-effort section - a failure here just leaves it hidden rather than
      // blocking the similar studies.
      getReferencedStudiesByReportId(reportIdNumber).catch(() => []),
    ])
      .then(([similar, referencedStudies]) => {
        if (cancelled) return;
        setLoaded({
          reportId: reportIdNumber,
          studies: similar.items,
          nextCursor: similar.nextCursor,
          referencedStudies,
        });
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

  const handleLoadMore = () => {
    if (!loaded?.nextCursor || loaded.reportId !== reportIdNumber || isLoadingMore) return;

    setIsLoadingMore(true);
    getSimilarStudiesByReportId(reportIdNumber, undefined, {
      params: { limit: PAGE_SIZE, cursor: loaded.nextCursor },
    })
      .then((response) => {
        // Not into the studies of a report opened since.
        setLoaded((prev) =>
          prev?.reportId === reportIdNumber
            ? { ...prev, studies: [...prev.studies, ...response.items], nextCursor: response.nextCursor }
            : prev
        );
      })
      .catch((error) => {
        console.error(`Error loading more studies for report ${reportIdNumber}:`, error);
        toast.error("Failed to load more studies");
      })
      .finally(() => {
        setIsLoadingMore(false);
      });
  };

  // The report's actions (e.g. a floating button of an extension) stand outside the studies, which fade while they
  // load, so they stay put from the moment the report opens.
  const actions = (
    <ReportActionsSlot
      key={reportIdNumber}
      reportId={reportIdNumber}
      studies={loaded?.reportId === reportIdNumber ? loaded.studies : []}
    />
  );

  if (notFound) {
    return (
      <div className="flex min-h-[40vh] w-full items-center justify-center text-sm text-muted-foreground">
        Report not found.
      </div>
    );
  }

  if (loadError) {
    return (
      <>
        <div className="flex min-h-[40vh] w-full items-center justify-center text-sm text-muted-foreground">
          Failed to load studies for this report.
        </div>
        {actions}
      </>
    );
  }

  if (loaded === null) {
    return (
      <>
        <StudyColumnSkeleton />
        {actions}
      </>
    );
  }

  // The last report's studies, while this one's load: shown faded (after a moment, so a quick load does not
  // flicker) and out of reach.
  const stale = loaded.reportId !== reportIdNumber;

  return (
    <>
      <div
        inert={stale}
        aria-busy={stale}
        className={cn(
          "motion-safe:transition-opacity motion-safe:duration-200",
          stale && "opacity-50 motion-safe:delay-150"
        )}
      >
        <div key={loaded.reportId} className="motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300">
          <CandidateStudyTable
            reportId={loaded.reportId}
            studies={loaded.studies}
            referencedStudies={loaded.referencedStudies}
            nextCursor={loaded.nextCursor}
            isLoadingMore={isLoadingMore}
            onLoadMore={handleLoadMore}
            inert={stale}
          />
        </div>
      </div>
      {actions}
    </>
  );
}
