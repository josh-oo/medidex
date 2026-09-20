import axios from "axios";
import { type ReactNode } from "react";
import { notFound } from "next/navigation";
import { adminGuard } from "@/guards/role.guard";
import { ReportColumnClient } from "./components/report-column-client";
import type { ProjectAnnotationsDto, ReportDetailDto } from "@/types/apiDTOs";
import {
  getAnnotations,
  getProjectReports 
} from "@/lib/api/projectApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";
import { ReviewAnnotationsProvider } from "./components/review-annotations-context";

interface PdfUploadPageProps {
  children: ReactNode;
  params: Promise<{
    projectId: string;
  }>;
}

interface ProjectReviewData {
  reports: ReportDetailDto[];
  annotations: ProjectAnnotationsDto;
}

async function loadProjectReports(projectId: string): Promise<ProjectReviewData> {
  const headers = await getMeerkatHeaders();

  try {
    const [reports, annotations] = await Promise.all([
      getProjectReports(projectId, false, { headers }),
      getAnnotations(projectId, { headers }),
    ]);

    const annotatedReportIds = new Set(Object.keys(annotations ?? {}));
    const filteredReports = (reports ?? []).filter((report) =>
      annotatedReportIds.has(String(report.report.reportId))
    );

    return {
      reports: filteredReports,
      annotations: annotations ?? {},
    };
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      notFound();
    }

    throw new Error("Failed to load project reports and annotations.");
  }
}

export default async function AnnotationsReviewPage({ children, params }: PdfUploadPageProps) {
  await adminGuard();

  const resolvedParams = await params;
  const projectId = resolvedParams?.projectId;

  if (!projectId) {
    notFound();
  }

  const { reports, annotations } = await loadProjectReports(projectId);

  return (
    <div className="h-full flex flex-col overflow-hidden">

      <div className="flex-1 min-h-0 bg-background">
        <ReviewAnnotationsProvider annotations={annotations}>
          <ReportColumnClient projectId={projectId} reports={reports}>
            {children}
          </ReportColumnClient>
        </ReviewAnnotationsProvider>
      </div>
    </div>
  );
}
