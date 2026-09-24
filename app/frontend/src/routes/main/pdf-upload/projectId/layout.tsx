import axios from "axios";
import { useEffect, useState } from "react";
import { useParams, Outlet } from "react-router-dom";
import { AdminGuard } from "@/components/auth/admin-guard";
import { ReportColumnClient } from "./components/report-column-client";
import type { ReportDetailDto } from "@/types/apiDTOs";
import { getProjectReports } from "@/lib/api/projectApi";
import { Spinner } from "@/components/ui/spinner";
import { useAuthStore } from "@/hooks/use-auth";

export default function PdfUploadPage() {
  const { projectId } = useParams<{ projectId: string }>() as { projectId: string };
  const isAdmin = useAuthStore((s) => s.user?.isAdmin ?? false);
  const [reports, setReports] = useState<ReportDetailDto[] | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    if (!isAdmin) return;

    let cancelled = false;
    setReports(null);
    setNotFound(false);

    getProjectReports(projectId, true)
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
  }, [projectId, isAdmin]);

  return (
    <AdminGuard>
      {notFound ? (
        <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
          Project not found.
        </div>
      ) : reports === null ? (
        <div className="flex h-full w-full items-center justify-center">
          <Spinner className="h-6 w-6" />
        </div>
      ) : (
        <div className="h-full flex flex-col overflow-hidden">
          <div className="flex-1 min-h-0 bg-background">
            <ReportColumnClient projectId={projectId} reports={reports}>
              <Outlet />
            </ReportColumnClient>
          </div>
        </div>
      )}
    </AdminGuard>
  );
}
