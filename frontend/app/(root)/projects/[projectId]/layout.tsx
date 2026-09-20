import { Suspense, type ReactNode } from "react";
import axios from "axios";
import { notFound } from "next/navigation";
import { ReportDetailDto } from "@/types/apiDTOs";
import { ReportColumnClient } from "./components/report-column-client";
import { getProjectReports as fetchProjectReports } from "@/lib/api/projectApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";
import { Skeleton } from "@/components/ui/skeleton";

interface ReportColumnProps {
    children: ReactNode;
    params: Promise<{
        projectId: string;
    }>;
}

async function getProjectReports(projectId: string): Promise<ReportDetailDto[]> {
    const headers = await getMeerkatHeaders();

    try {
        const reports = await fetchProjectReports(projectId, false, { headers });
        return reports ?? [];
    } catch (error) {
        if (axios.isAxiosError(error) && error.response?.status === 404) {
            notFound();
        }

        throw new Error("Failed to load project reports.");
    }
}

export default async function ReportColumn({ children, params }: ReportColumnProps) {
    const resolvedParams = await params;
    const projectId = resolvedParams?.projectId;

    if (!projectId) {
        notFound();
    }

    return (
        <Suspense fallback={<ReportColumnSkeleton />}>
            <ReportColumnContent projectId={projectId}>{children}</ReportColumnContent>
        </Suspense>
    );
}

async function ReportColumnContent({
    children,
    projectId,
}: {
    children: ReactNode;
    projectId: string;
}) {
    const reports = await getProjectReports(projectId);

    return (
        <ReportColumnClient projectId={projectId} reports={reports}>
            {children}
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