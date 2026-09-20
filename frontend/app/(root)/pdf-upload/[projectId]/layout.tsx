import axios from "axios";
import { type ReactNode } from "react";
import { notFound } from "next/navigation";
import { adminGuard } from "@/guards/role.guard";
import { ReportColumnClient } from "./components/report-column-client";
import type { ReportDetailDto } from "@/types/apiDTOs";
import { getProjectReports as fetchProjectReports } from "@/lib/api/projectApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

interface PdfUploadPageProps {
  children: ReactNode;
  params: Promise<{
    projectId: string;
  }>;
}

async function loadProjectReports(projectId: string): Promise<ReportDetailDto[]> {
  const headers = await getMeerkatHeaders();

  try {
    const reports = await fetchProjectReports(projectId, true, { headers });
    return reports ?? [];
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      notFound();
    }

    throw new Error("Failed to load project reports.");
  }
}

export default async function PdfUploadPage({ children, params }: PdfUploadPageProps) {
  await adminGuard();

  const resolvedParams = await params;
  const projectId = resolvedParams?.projectId;

  if (!projectId) {
    notFound();
  }

  const reports = await loadProjectReports(projectId);

  return (
    <div className="h-full flex flex-col overflow-hidden">

      <div className="flex-1 min-h-0 bg-background">
        <ReportColumnClient projectId={projectId} reports={reports}>
          {children}
        </ReportColumnClient>
      </div>
    </div>
  );
}

function PdfUploadPlaceholder() {
  return (
    <div className="h-full flex flex-col items-center justify-center px-8 text-center gap-3">
      <div className="space-y-2 max-w-md">
        <h2 className="text-lg font-semibold text-foreground">Select a report</h2>
        <p className="text-sm text-muted-foreground">
          Choose a report from the list to view its metadata, attach PDFs, or confirm that uploads are complete.
        </p>
      </div>
    </div>
  );
}
