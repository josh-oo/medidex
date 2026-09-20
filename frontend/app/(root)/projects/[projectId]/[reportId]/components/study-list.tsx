import axios from "axios";
import { notFound } from "next/navigation";
import { StudyRelevanceTable } from "@/components/ui/study-view/study-relevance-table";
import { Skeleton } from "@/components/ui/skeleton";
import type { SimilarStudyDto } from "@/types/apiDTOs";
import type { RelevanceStudy } from "@/types/reports";
import { getSimilarStudiesByReportId } from "@/lib/api/reportApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";
import { ReportChatButtons } from "./ai-actions";

interface StudyListProps {
  params: {
    projectId: string;
    reportId: string;
  };
  searchParams: {
    k?: string;
  };
}

const mapResponseToRelevanceStudies = (
  response: SimilarStudyDto[]
): RelevanceStudy[] => {
  return response.map((study) => ({
    ...study,
    isLinked: false
  }));
};

export default async function StudyList({ params, searchParams }: StudyListProps) {

  const { projectId, reportId } = await params;
  const { k } = await searchParams;
  const source = projectId;
  const reportIdNumber = Number(reportId);

  const headers = await getMeerkatHeaders();
  let response: SimilarStudyDto[] = [];

  try {
    response = await getSimilarStudiesByReportId(reportIdNumber, undefined, {
      headers,
      params: { k, source },
    });
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      notFound();
    }

    throw error;
  }

  const studies = mapResponseToRelevanceStudies(response);

  return (
    <>
      <StudyRelevanceTable
        reportId={reportIdNumber}
        studies={studies}
      />
      <ReportChatButtons reportId={reportIdNumber} studies={studies}/>
    </>
  );
}

export function StudyListSkeleton() {
  const rowPlaceholders = Array.from({ length: 7 });

  return (
    <div className="h-full flex flex-col min-w-0 overflow-hidden pt-5">
      <div className="px-4 pb-4 border-b border-border space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <Skeleton className="h-6 w-6 rounded" />
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-5 w-10 rounded-full" />
          </div>
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-24 rounded-md" />
            <Skeleton className="h-8 w-32 rounded-md" />
            <Skeleton className="h-8 w-20 rounded-md" />
          </div>
        </div>
        <Skeleton className="h-9 w-full rounded-md" />
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto px-4">
        <div className="pt-3 pb-4 space-y-3">
        {rowPlaceholders.map((_, index) => (
          <div
            key={index}
            className="rounded-lg border border-border/60 bg-card p-4"
          >
            <div className="flex items-start">
              <div className="flex-1 min-w-0 space-y-3">
                <div className="flex items-center gap-2">
                  <Skeleton className="h-5 w-2/5" />
                  <Skeleton className="h-5 w-24 rounded-full" />
                  <Skeleton className="h-5 w-16 rounded-full" />
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-2">
                  <div className="flex items-center gap-1.5">
                    <Skeleton className="h-4 w-4 rounded" />
                    <Skeleton className="h-4 w-32" />
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Skeleton className="h-4 w-4 rounded" />
                    <Skeleton className="h-4 w-24" />
                  </div>
                  <div className="flex items-center gap-1.5 min-w-[180px] flex-1">
                    <Skeleton className="h-4 w-4 rounded" />
                    <Skeleton className="h-4 w-full max-w-[260px]" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}

          <div className="pt-1">
            <Skeleton className="h-9 w-44 rounded-md" />
          </div>
        </div>
      </div>
    </div>
  );
}
