import { useEffect, useState } from "react";
import axios from "axios";
import { useParams, Outlet } from "react-router-dom";
import { ReportDetailDto } from "@/types/apiDTOs";
import { ReportColumnClient } from "./components/report-column-client";
import { getProjectReports } from "@/lib/api/projectApi";
import { Skeleton } from "@/components/ui/skeleton";

export default function ReportColumn() {
  const { projectId } = useParams<{ projectId: string }>() as { projectId: string };
  const [reports, setReports] = useState<ReportDetailDto[] | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setReports(null);
    setNotFound(false);

    getProjectReports(projectId, false)
      .then((result) => {
        if (!cancelled) setReports(result ?? []);
      })
      .catch((error) => {
        if (cancelled) return;
        if (axios.isAxiosError(error) && error.response?.status === 404) {
          setNotFound(true);
        } else {
          console.error("Failed to load project reports:", error);
          setReports([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  if (notFound) {
    return (
      <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
        Project not found.
      </div>
    );
  }

  if (reports === null) {
    return <ReportColumnSkeleton />;
  }

  return (
    <ReportColumnClient projectId={projectId} reports={reports}>
      <Outlet />
    </ReportColumnClient>
  );
}

function ReportColumnSkeleton() {
    const rowPlaceholders = Array.from({ length: 7 });

    return (
        <div className="h-full w-full flex min-w-0 bg-background">
            <div className="min-w-0 flex-[0_0_55%] border-r">
                <div className="h-full flex flex-col pt-5">
                    <div className="px-4 pb-4 border-b border-border space-y-4">
                        <div className="flex items-center gap-2">
                            <Skeleton className="h-6 w-6 rounded" />
                            <Skeleton className="h-7 w-24" />
                            <Skeleton className="h-5 w-10" />
                        </div>

                        <div className="space-y-3">
                            <Skeleton className="h-9 w-full rounded-md" />
                            <div className="flex flex-wrap gap-2 sm:flex-nowrap sm:items-center sm:gap-4">
                                <Skeleton className="h-4 w-10" />
                                <div className="flex gap-1">
                                    <Skeleton className="h-7 w-12 rounded-md" />
                                    <Skeleton className="h-7 w-16 rounded-md" />
                                    <Skeleton className="h-7 w-20 rounded-md" />
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 min-h-0 overflow-hidden px-4">
                        <div className="space-y-3 pb-4 pt-3">
                            {rowPlaceholders.map((_, index) => (
                                <div
                                    key={index}
                                    className="rounded-lg border border-border bg-card p-4"
                                >
                                    <div className="space-y-3">
                                        <div className="flex items-start justify-between gap-3">
                                            <Skeleton className="h-5 w-4/5" />
                                            <Skeleton className="h-8 w-8 rounded-md" />
                                        </div>

                                        <div className="flex items-center gap-3 flex-wrap">
                                            <div className="flex items-center gap-1.5">
                                                <Skeleton className="h-3.5 w-3.5 rounded" />
                                                <Skeleton className="h-4 w-12" />
                                            </div>
                                            <div className="flex items-center gap-1.5">
                                                <Skeleton className="h-3.5 w-3.5 rounded" />
                                                <Skeleton className="h-4 w-36" />
                                            </div>
                                        </div>

                                        <Skeleton className="h-4 w-full" />
                                        <Skeleton className="h-4 w-5/6" />

                                        <div className="flex flex-wrap gap-2 pt-1">
                                            <Skeleton className="h-5 w-20 rounded-full" />
                                            <Skeleton className="h-5 w-24 rounded-full" />
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            <div className="min-w-0 flex-[0_0_45%]">
                <ReportDetailsPanelSkeleton />
            </div>
        </div>
    );
}

function ReportDetailsPanelSkeleton() {
    return (
        <div className="h-full flex flex-col min-w-0 overflow-hidden p-4 md:px-8">
            <div className="space-y-2">
                <Skeleton className="h-6 w-36" />
                <Skeleton className="h-4 w-52" />
            </div>
            <div className="flex-1 mt-4 space-y-4 overflow-hidden">
                <Skeleton className="h-24 w-full rounded-xl" />
                <Skeleton className="h-24 w-full rounded-xl" />
                <Skeleton className="h-24 w-full rounded-xl" />
            </div>
        </div>
    );
}
