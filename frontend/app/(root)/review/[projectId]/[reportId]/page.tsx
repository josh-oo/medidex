"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyTitle,
} from "@/components/ui/empty";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useDetailsSheet } from "@/app/context/details-sheet-context";
import {
  useReviewAnnotations,
  useReviewAnnotationsActions,
} from "../components/review-annotations-context";
import { useReportStore } from "@/hooks/use-report-store";
import type { StudyDto } from "@/types/apiDTOs";
import { Calendar, Scale, CircleCheckBig, CircleAlert, TriangleAlert, Users, Info, AlertTriangle } from "lucide-react";

interface GroupedUserStudy {
  userId: string;
  userName: string;
  studies: Array<{ studyId: number; studyShortName: string }>;
}

type UsersResponse = {
  users?: Array<{ id: string; name: string }>;
};

interface FinalDecisionStudyItem {
  study: StudyDto;
  selectedBy: string[];
  isUnanimous: boolean;
}

const formatParticipantCount = (value?: string | null) => {
  if (!value) return "-";
  const numericValue = Number(value.replace(/,/g, ""));
  if (Number.isFinite(numericValue)) {
    return numericValue.toLocaleString();
  }
  return value;
};

const getStudyConfirmationPath = (reportId: string, studyId: number) =>
  `/api/meerkat/reports/${reportId}/studies/${studyId}/confirmation`;

const toggleStudyConfirmation = async (
  reportId: string,
  studyId: number,
  shouldConfirm: boolean
) => {
  const response = await fetch(getStudyConfirmationPath(reportId, studyId), {
    method: shouldConfirm ? "PUT" : "DELETE",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });

  if (response.ok) {
    return;
  }

  let detail = `Failed to ${shouldConfirm ? "confirm" : "unconfirm"} study`;
  try {
    const payload = await response.json();
    if (payload?.error) {
      detail = payload.error;
    }
  } catch (error) {
    console.error("Failed to parse confirmation toggle error payload", error);
  }

  throw new Error(detail);
};

export default function ReviewDetailsPage() {
  const annotations = useReviewAnnotations();
  const { updateConfirmedForReportStudy } = useReviewAnnotationsActions();
  const params = useParams();
  const router = useRouter();
  const { openWithStudyId } = useDetailsSheet();

  const [userNameById, setUserNameById] = useState<Map<string, string>>(new Map());
  const [studyById, setStudyById] = useState<Record<number, StudyDto>>({});
  const [loadingStudyIds, setLoadingStudyIds] = useState<Set<number>>(new Set());
  const [selectedFinalStudyIds, setSelectedFinalStudyIds] = useState<Set<number>>(new Set());
  const [syncingFinalStudyIds, setSyncingFinalStudyIds] = useState<Set<number>>(new Set());
  const [isDeletingReport, setIsDeletingReport] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [deleteReportError, setDeleteReportError] = useState<string | null>(null);

  const toTimestamp = (value: Date | string | number | null | undefined): number | null => {
    if (value === null || value === undefined) {
      return null;
    }
    const date = value instanceof Date ? value : new Date(value);
    const timestamp = date.getTime();
    return Number.isFinite(timestamp) ? timestamp : null;
  };

  useEffect(() => {
    let isMounted = true;

    const loadUsers = async () => {
      try {
        const response = await fetch("/api/users", { cache: "no-store" });
        if (!response.ok) return;

        const data = (await response.json()) as UsersResponse;
        const nextMap = new Map<string, string>();

        for (const user of data.users ?? []) {
          nextMap.set(user.id, user.name);
        }

        if (isMounted) {
          setUserNameById(nextMap);
        }
      } catch (error) {
        console.error("Failed to resolve user names:", error);
      }
    };

    void loadUsers();

    return () => {
      isMounted = false;
    };
  }, []);

  const reportIdParam =
    typeof params.reportId === "string"
      ? params.reportId
      : Array.isArray(params.reportId)
      ? params.reportId[0]
      : undefined;

  const projectIdParam =
    typeof params.projectId === "string"
      ? params.projectId
      : Array.isArray(params.projectId)
      ? params.projectId[0]
      : undefined;

  const reportId = useMemo(() => {
    if (!reportIdParam) return null;
    const parsed = Number.parseInt(reportIdParam, 10);
    return Number.isNaN(parsed) ? null : parsed;
  }, [reportIdParam]);

  const reportCreatedAt = useReportStore((state) =>
    reportId === null ? undefined : state.reports[reportId]?.report.createdAt
  );

  useEffect(() => {
    if (!reportIdParam) {
      setSelectedFinalStudyIds(new Set());
      return;
    }

    const confirmedStudyIds = new Set<number>();
    for (const annotation of annotations[reportIdParam]?.studies ?? []) {
      if (annotation.confirmed) {
        confirmedStudyIds.add(annotation.studyId);
      }
    }

    setSelectedFinalStudyIds(confirmedStudyIds);
  }, [annotations, reportIdParam]);

  const groupedByUser = useMemo<GroupedUserStudy[]>(() => {
    if (!reportIdParam) {
      return [];
    }

    const reportAnnotations = annotations[reportIdParam]?.studies ?? [];
    const userToStudies = new Map<string, Map<number, string>>();

    for (const annotation of reportAnnotations) {
      if (!userToStudies.has(annotation.user)) {
        userToStudies.set(annotation.user, new Map<number, string>());
      }
      userToStudies
        .get(annotation.user)
        ?.set(annotation.studyId, annotation.studyShortName);
    }

    return Array.from(userToStudies.entries())
      .map(([userId, studiesMap]) => ({
        userId,
        userName: userNameById.get(userId) ?? "Unknown user",
        studies: Array.from(studiesMap.entries())
          .map(([studyId, studyShortName]) => ({ studyId, studyShortName }))
          .sort((a, b) => a.studyShortName.localeCompare(b.studyShortName)),
      }))
      .sort((a, b) => a.userName.localeCompare(b.userName));
  }, [annotations, reportIdParam, userNameById]);

  const reportFlags = useMemo<string[]>(() => {
    if (!reportIdParam) {
      return [];
    }

    const flags = annotations[reportIdParam]?.flags ?? [];
    const uniqueFlags = new Set<string>();

    for (const annotationFlag of flags) {
      const trimmedFlag = annotationFlag.flag?.trim();
      if (!trimmedFlag) {
        continue;
      }

      uniqueFlags.add(trimmedFlag);
    }

    return Array.from(uniqueFlags.values()).sort((a, b) => a.localeCompare(b));
  }, [annotations, reportIdParam]);

  const studyIdsToLoad = useMemo(() => {
    const ids = new Set<number>();

    for (const group of groupedByUser) {
      for (const study of group.studies) {
        ids.add(study.studyId);
      }
    }

    return Array.from(ids);
  }, [groupedByUser]);

  useEffect(() => {
    if (studyIdsToLoad.length === 0) {
      setStudyById({});
      setLoadingStudyIds(new Set());
      return;
    }

    const missingStudyIds = studyIdsToLoad.filter((studyId) => !studyById[studyId]);
    if (missingStudyIds.length === 0) {
      return;
    }

    let isMounted = true;
    setLoadingStudyIds((prev) => {
      const next = new Set(prev);
      for (const studyId of missingStudyIds) {
        next.add(studyId);
      }
      return next;
    });

    const loadStudies = async () => {
      const entries = await Promise.all(
        missingStudyIds.map(async (studyId) => {
          try {
            const response = await fetch(`/api/meerkat/studies/${studyId}`, {
              cache: "no-store",
            });

            if (!response.ok) {
              throw new Error(`Failed to load study ${studyId}`);
            }

            const data = (await response.json()) as StudyDto;
            return [studyId, data] as const;
          } catch (error) {
            console.error(`Failed to resolve study ${studyId}:`, error);
            return null;
          }
        })
      );

      if (!isMounted) return;

      setStudyById((prev) => {
        const next = { ...prev };
        for (const entry of entries) {
          if (!entry) continue;
          const [studyId, study] = entry;
          next[studyId] = study;
        }
        return next;
      });
      setLoadingStudyIds((prev) => {
        const next = new Set(prev);
        for (const studyId of missingStudyIds) {
          next.delete(studyId);
        }
        return next;
      });
    };

    void loadStudies();

    return () => {
      isMounted = false;
    };
  }, [studyById, studyIdsToLoad]);

  const finalDecisionStudies = useMemo<FinalDecisionStudyItem[]>(() => {
    const totalAnnotators = groupedByUser.length;

    return studyIdsToLoad
      .map((studyId) => {
        const study = studyById[studyId];
        if (!study) return null;

        const selectedBy = groupedByUser
          .filter((group) => group.studies.some((studyRef) => studyRef.studyId === studyId))
          .map((group) => group.userName)
          .sort((a, b) => a.localeCompare(b));

        return {
          study,
          selectedBy,
          isUnanimous: totalAnnotators > 0 && selectedBy.length === totalAnnotators,
        };
      })
      .filter((item): item is FinalDecisionStudyItem => Boolean(item))
      .sort((a, b) => a.study.shortName.localeCompare(b.study.shortName));
  }, [groupedByUser, studyById, studyIdsToLoad]);

  const isLoadingFreshStudies = studyIdsToLoad.length > 0 && loadingStudyIds.size > 0;

  const toggleFinalStudySelection = async (studyId: number) => {
    if (!reportIdParam || syncingFinalStudyIds.has(studyId)) {
      return;
    }

    const wasSelected = selectedFinalStudyIds.has(studyId);
    const shouldConfirm = !wasSelected;

    setSyncingFinalStudyIds((prev) => {
      const next = new Set(prev);
      next.add(studyId);
      return next;
    });

    try {
      await toggleStudyConfirmation(reportIdParam, studyId, shouldConfirm);
      setSelectedFinalStudyIds((prev) => {
        const next = new Set(prev);
        if (shouldConfirm) {
          next.add(studyId);
        } else {
          next.delete(studyId);
        }
        return next;
      });
      updateConfirmedForReportStudy(reportIdParam, studyId, shouldConfirm);
    } catch (error) {
      console.error("Failed to sync study confirmation state:", error);
    } finally {
      setSyncingFinalStudyIds((prev) => {
        const next = new Set(prev);
        next.delete(studyId);
        return next;
      });
    }
  };

  const handleDeleteReport = async () => {
    if (!reportIdParam || isDeletingReport) {
      return;
    }

    setIsDeletingReport(true);
    setDeleteReportError(null);
    try {
      const response = await fetch(`/api/meerkat/reports/${reportIdParam}`, {
        method: "DELETE",
      });

      if (!response.ok) {
        throw new Error("Failed to delete report.");
      }

      setIsDeleteDialogOpen(false);

      if (projectIdParam) {
        router.push(`/review/${projectIdParam}`);
      } else {
        router.push("/review");
      }
      router.refresh();
    } catch (error) {
      console.error("Failed to delete report:", error);
      setDeleteReportError("Unable to delete report. Please try again.");
    } finally {
      setIsDeletingReport(false);
    }
  };

  if (!reportIdParam) {
    return (
      <div className="h-full p-6">
        <Empty className="h-full border">
          <EmptyHeader>
            <EmptyTitle>No report selected</EmptyTitle>
            <EmptyDescription>
              Select a report from the list to view assigned studies by annotator.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      </div>
    );
  }

  return (
    <div className="pt-4">
      <div className="px-4 pb-2 border-b border-border">
        <div className="flex items-center gap-2">
          <CircleCheckBig className="h-6 w-6 text-primary" />
          <h2 className="text-xl font-semibold">Review Annotations</h2>
        </div>
      </div>

      <div className="px-4 py-4">
        {reportFlags.length > 0 ? (
          <section className="mb-8 space-y-4 rounded-none border border-border bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-sm font-semibold uppercase tracking-wide text-foreground">
                  Report Flags
                </h3>
                <p className="mt-1 text-sm text-muted-foreground">
                  Flags raised by annotators that may influence your final decision.
                </p>
              </div>
            </div>

            <div className="space-y-3">
              {reportFlags.map((flag) => (
                <div
                  key={`report-flag-${flag}`}
                  className="flex items-start gap-2 rounded-md border border-primary/30 bg-primary/10 p-2"
                >
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <p className="text-sm font-medium text-primary">{flag}</p>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <section className="mb-8 space-y-4 rounded-none border border-border bg-white p-4 shadow-sm">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-foreground">
                Final Selection
              </h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Select one or more studies from the annotator suggestions.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8"
                onClick={() => setSelectedFinalStudyIds(new Set())}
                disabled={selectedFinalStudyIds.size === 0 || isDeletingReport}
              >
                Clear
              </Button>
            </div>
          </div>

          {groupedByUser.length === 0 ? (
            <Empty className="border">
              <EmptyHeader>
                <EmptyTitle>No annotations found</EmptyTitle>
                <EmptyDescription>
                  This report does not have annotation assignments yet.
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : isLoadingFreshStudies && finalDecisionStudies.length === 0 ? (
            <div className="space-y-3">
              {studyIdsToLoad.slice(0, 4).map((studyId) => (
                <div
                  key={`loading-study-${studyId}`}
                  className="rounded-lg border border-border bg-card p-4"
                >
                  <div className="flex flex-col gap-3">
                    <div className="flex items-start gap-3">
                      <Skeleton className="h-6 flex-1" />
                      <Skeleton className="h-6 w-6 shrink-0" />
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                      <Skeleton className="h-4 w-28" />
                      <Skeleton className="h-4 w-24" />
                      <Skeleton className="h-4 w-56" />
                    </div>
                    <div className="border-t border-border/60 pt-2">
                      <Skeleton className="h-4 w-64" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : finalDecisionStudies.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border/70 bg-background/60 p-4 text-sm text-muted-foreground">
              No study suggestions available yet.
            </div>
          ) : (
            <div className="space-y-3">
              {finalDecisionStudies.map((item) => {
                const isLoading = loadingStudyIds.has(item.study.studyId) || !studyById[item.study.studyId];
                const isSelected = selectedFinalStudyIds.has(item.study.studyId);
                const isSyncing = syncingFinalStudyIds.has(item.study.studyId);
                const studyTimestamp = toTimestamp(item.study.createdAt);
                const reportTimestamp = toTimestamp(reportCreatedAt);
                const shouldShowNewHint =
                  studyTimestamp !== null &&
                  reportTimestamp !== null &&
                  studyTimestamp > reportTimestamp;
                const rowClass = isSelected
                  ? "border-emerald-300 bg-emerald-100"
                  : item.isUnanimous
                  ? "border-border bg-emerald-50/20 hover:bg-emerald-50/35"
                  : "border-border bg-amber-50/40 hover:bg-amber-50/60";

                return (
                  <div
                    key={item.study.studyId}
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSelected}
                    aria-label={isSelected ? `Deselect ${item.study.shortName}` : `Select ${item.study.shortName}`}
                    onClick={() => {
                      void toggleFinalStudySelection(item.study.studyId);
                    }}
                    onKeyDown={(event) => {
                      if (isSyncing) {
                        return;
                      }
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        void toggleFinalStudySelection(item.study.studyId);
                      }
                    }}
                    className={`p-4 bg-card rounded-lg relative w-full max-w-full overflow-hidden transition-all duration-200 border flex items-center gap-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${isSyncing ? "cursor-wait opacity-70" : "cursor-pointer"} ${rowClass}`}
                  >
                    {isLoading ? (
                      <div className="flex flex-1 min-w-0 flex-col gap-3">
                        <div className="flex items-start gap-3">
                          <Skeleton className="h-6 flex-1" />
                          <Skeleton className="h-6 w-6 shrink-0" />
                        </div>
                        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                          <Skeleton className="h-4 w-28" />
                          <Skeleton className="h-4 w-24" />
                          <Skeleton className="h-4 w-64" />
                        </div>
                        <div className="border-t border-border/60 pt-2">
                          <Skeleton className="h-4 w-64" />
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="flex flex-col gap-3 flex-1 min-w-0">
                          <div className="flex items-start gap-3">
                            <div className="flex-1 min-w-0">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <h4 className="text-base font-semibold max-w-full">
                                    <span className="inline-flex w-full min-w-0 items-center">
                                      <span className="truncate">{item.study.shortName}</span>
                                    </span>
                                  </h4>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p>{item.study.shortName}</p>
                                </TooltipContent>
                              </Tooltip>
                            </div>

                            <Tooltip>
                              <TooltipTrigger asChild>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="h-6 w-6 shrink-0 text-muted-foreground hover:bg-transparent hover:text-black"
                                  aria-label={`Open details for ${item.study.shortName}`}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    openWithStudyId(item.study.studyId);
                                  }}
                                >
                                  <Info className="h-3.5 w-3.5" />
                                </Button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p>Open study details</p>
                              </TooltipContent>
                            </Tooltip>
                          </div>

                          <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs w-full">
                            <div className="flex items-center gap-1.5 text-muted-foreground">
                              <div className="p-0.5">
                                <Users className="h-3 w-3" />
                              </div>
                              <span>{formatParticipantCount(item.study.numberParticipants)} participants</span>
                            </div>

                            <div className="flex items-center gap-1.5 text-muted-foreground">
                              <div className="p-0.5 rounded">
                                <Calendar className={`h-3 w-3 ${item.study.duration ? "" : "text-muted-foreground/50"}`} />
                              </div>
                              <span className={item.study.duration ? "" : "text-muted-foreground/50"}>
                                {item.study.duration || "No duration"}
                              </span>
                            </div>

                            {item.study.comparison && (
                              <div className="flex items-center gap-1.5 text-muted-foreground flex-1 min-w-0 basis-0 max-w-full overflow-hidden">
                                <div className="p-0.5 rounded">
                                  <Scale className="h-3 w-3" />
                                </div>
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <span className="truncate block w-full max-w-full">
                                      {item.study.comparison}
                                    </span>
                                  </TooltipTrigger>
                                  <TooltipContent className="max-w-xs">
                                    <p>{item.study.comparison}</p>
                                  </TooltipContent>
                                </Tooltip>
                              </div>
                            )}
                          </div>

                          <div className="border-t border-border/60 pt-2">
                            {item.isUnanimous ? (
                              <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-700">
                                {shouldShowNewHint ? (
                                  <span
                                    className="mr-2 inline-flex items-center gap-1.5 text-amber-700"
                                  >
                                    <TriangleAlert className="h-3.5 w-3.5" />
                                    <span className="italic">new</span>
                                  </span>
                                ) : null}
                                <CircleCheckBig className="h-3.5 w-3.5" />
                                <span>Consensus (all annotators selected this study)</span>
                              </div>
                            ) : (
                              <div
                                className="flex items-center gap-1.5 text-xs font-medium"
                                style={{ color: isSelected ? "black" : "sienna" }}
                              >
                                {shouldShowNewHint ? (
                                  <span className="mr-2 inline-flex items-center gap-1.5">
                                    <TriangleAlert className="h-3.5 w-3.5" />
                                    <span className="italic">new</span>
                                  </span>
                                ) : null}
                                <CircleAlert className="h-3.5 w-3.5" />
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <span className="cursor-help">
                                      No consensus ({item.selectedBy.length} of {groupedByUser.length} annotators selected this study)
                                    </span>
                                  </TooltipTrigger>
                                  <TooltipContent className="max-w-xs">
                                    <p>Selected by: {item.selectedBy.join(", ")}</p>
                                  </TooltipContent>
                                </Tooltip>
                              </div>
                            )}
                          </div>
                        </div>

                      </>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </section>

        <div className="mt-4 flex justify-center">
          <AlertDialog
            open={isDeleteDialogOpen}
            onOpenChange={(nextOpen) => {
              setIsDeleteDialogOpen(nextOpen);
              if (!nextOpen) {
                setDeleteReportError(null);
              }
            }}
          >
            <AlertDialogTrigger asChild>
              <Button
                type="button"
                variant="outline"
                className="h-10 border-destructive/30 bg-white px-6 text-destructive shadow-none hover:bg-destructive/10 hover:shadow-none"
                disabled={isDeletingReport}
              >
                Delete Report
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent
              className="sm:max-w-md"
              onClick={(event) => event.stopPropagation()}
            >
              <AlertDialogHeader>
                <div className="mb-2 flex items-center gap-2 text-destructive">
                  <AlertTriangle className="h-4 w-4" aria-hidden />
                  <span className="text-xs font-semibold uppercase tracking-wide">Danger Zone</span>
                </div>
                <AlertDialogTitle>Delete this report?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will permanently remove all data for this report.
                </AlertDialogDescription>
                <div className="mt-2 rounded-md border border-border/70 bg-muted/30 px-3 py-2 text-sm text-foreground">
                  Report ID: {reportIdParam}
                </div>
                {deleteReportError ? (
                  <p className="mt-2 text-sm text-destructive">{deleteReportError}</p>
                ) : null}
              </AlertDialogHeader>
              <AlertDialogFooter className="gap-2 sm:gap-2">
                <AlertDialogCancel disabled={isDeletingReport}>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={(event) => {
                    event.preventDefault();
                    void handleDeleteReport();
                  }}
                  disabled={isDeletingReport}
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                >
                  {isDeletingReport ? "Deleting..." : "Delete"}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>
    </div>
  );
}
