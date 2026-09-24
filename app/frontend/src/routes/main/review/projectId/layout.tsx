import axios from "axios";
import { useEffect, useState } from "react";
import { useParams, Outlet } from "react-router-dom";
import { AdminGuard } from "@/components/auth/admin-guard";
import { ReportColumnClient } from "./components/report-column-client";
import type { ProjectAnnotationsDto, ReportDetailDto } from "@/types/apiDTOs";
import { getAnnotations, getProjectReports } from "@/lib/api/projectApi";
import { ReviewAnnotationsProvider } from "./components/review-annotations-context";
import { Spinner } from "@/components/ui/spinner";
import { useAuthStore } from "@/hooks/use-auth";

interface ProjectReviewData {
  reports: ReportDetailDto[];
  annotations: ProjectAnnotationsDto;
}

export default function AnnotationsReviewPage() {
  const { projectId } = useParams<{ projectId: string }>() as { projectId: string };
  const isAdmin = useAuthStore((s) => s.user?.isAdmin ?? false);
  const [data, setData] = useState<ProjectReviewData | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!isAdmin) return;

    let cancelled = false;
    setData(null);
    setNotFound(false);

    (async () => {
      try {
        const [reports, annotations] = await Promise.all([
          getProjectReports(projectId, false),
          getAnnotations(projectId),
        ]);

        const annotatedReportIds = new Set(Object.keys(annotations ?? {}));
        const filteredReports = (reports ?? []).filter((report) =>
          annotatedReportIds.has(String(report.report.reportId))
        );

        if (!cancelled) {
          setData({ reports: filteredReports, annotations: annotations ?? {} });
        }
      } catch (error) {
        if (cancelled) return;
        if (axios.isAxiosError(error) && error.response?.status === 404) {
          setNotFound(true);
        } else {
          console.error("Failed to load project reports and annotations:", error);
          setData({ reports: [], annotations: {} });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [projectId, isAdmin]);

  return (
    <AdminGuard>
      {notFound ? (
        <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
          Project not found.
        </div>
      ) : data === null ? (
        <div className="flex h-full w-full items-center justify-center">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <div className="h-full flex flex-col overflow-hidden">
          <div className="flex-1 min-h-0 bg-background">
            <ReviewAnnotationsProvider annotations={data.annotations}>
              <ReportColumnClient projectId={projectId} reports={data.reports}>
                <Outlet />
              </ReportColumnClient>
            </ReviewAnnotationsProvider>
          </div>
        </div>
      )}
    </AdminGuard>
  );
}
