import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { StudyCardGraph } from "@/components/ui/study-view/study-graph";
import { useParams, useNavigate } from "react-router-dom";
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
import { useDetailsSheet } from "@/context/details-sheet-context";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import {
  useReviewAnnotations,
  useReviewAnnotationsActions,
} from "../components/review-annotations-context";
import { useReportStore } from "@/hooks/use-report-store";
import type { StudyDto } from "@/types/apiDTOs";
import { Calendar, CircleCheckBig, CircleAlert, TriangleAlert, Users, Info, AlertTriangle, Flag, Trash2, GitMerge } from "lucide-react";
import { Widget } from "@/components/ui/widget";
import { getStudyById } from "@/lib/api/studiesApi";
import { curationPaths } from "@/lib/curation-steps";
import { deleteReportById, mergeReport } from "@/lib/api/reportApi";

interface GroupedUserStudy {
  userId: string;
  userName: string;
  studies: Array<{ studyId: number; studyShortName: string }>;
}

// A study the annotators chose for the report. All but its details are known from the annotations, so its row is
// there (at its full size) before the study is loaded.
interface FinalDecisionStudyItem {
  studyId: number;
  shortName: string;
  /** The study: undefined while it loads, null when it could not be. */
  study: StudyDto | null | undefined;
  selectedBy: string[];
  isUnanimous: boolean;
}

const formatParticipantCount = (value?: number | null) => (value == null ? "-" : value.toLocaleString());

export default function ReviewDetailsPage() {
  const annotations = useReviewAnnotations();
  const { reportFinished } = useReviewAnnotationsActions();
  const params = useParams();
  const navigate = useNavigate();
  const { openWithStudyId } = useDetailsSheet();

  // A study that could not be loaded is null.
  const [studyById, setStudyById] = useState<Record<number, StudyDto | null>>({});
  // The studies to merge the report with: chosen here, sent with the merge (nothing is saved before).
  const [selectedFinalStudyIds, setSelectedFinalStudyIds] = useState<Set<number>>(new Set());
  const [isDeletingReport, setIsDeletingReport] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [deleteReportError, setDeleteReportError] = useState<string | null>(null);
  const [isMerging, setIsMerging] = useState(false);
  const [mergeError, setMergeError] = useState<string | null>(null);
  const { reviewPanels } = useExtensionRegistry();
  // Why the panels of the extensions hold the merge back, by panel.
  const [mergeBlocks, setMergeBlocks] = useState<Record<number, string | null>>({});
  const mergeBlock = Object.values(mergeBlocks).find((reason) => reason) ?? null;
  const selectedStudyIdList = useMemo(() => [...selectedFinalStudyIds].sort((a, b) => a - b), [selectedFinalStudyIds]);
  const blockMerge = useMemo(
    () => reviewPanels.map((_, index) => (reason: string | null) => setMergeBlocks((current) => ({ ...current, [index]: reason }))),
    [reviewPanels],
  );

  const toTimestamp = (value: Date | string | number | null | undefined): number | null => {
    if (value === null || value === undefined) {
      return null;
    }
    const date = value instanceof Date ? value : new Date(value);
    const timestamp = date.getTime();
    return Number.isFinite(timestamp) ? timestamp : null;
  };

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
    reportId === null ? undefined : state.reports[reportId]?.createdAt
  );

  useEffect(() => {
    setSelectedFinalStudyIds(new Set());
  }, [reportIdParam]);

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

    // The review is blind: the annotators are numbered, not named.
    return Array.from(userToStudies.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([userId, studiesMap], index) => ({
        userId,
        userName: `Annotator ${index + 1}`,
        studies: Array.from(studiesMap.entries())
          .map(([studyId, studyShortName]) => ({ studyId, studyShortName }))
          .sort((a, b) => a.studyShortName.localeCompare(b.studyShortName)),
      }))
  }, [annotations, reportIdParam]);

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
      return;
    }

    const missingStudyIds = studyIdsToLoad.filter((studyId) => !(studyId in studyById));
    if (missingStudyIds.length === 0) {
      return;
    }

    let isMounted = true;

    const loadStudies = async () => {
      const entries = await Promise.all(
        missingStudyIds.map(async (studyId) => {
          try {
            const data = await getStudyById(studyId);
            return [studyId, data] as const;
          } catch (error) {
            console.error(`Failed to resolve study ${studyId}:`, error);
            return [studyId, null] as const;
          }
        })
      );

      if (!isMounted) return;

      setStudyById((prev) => ({ ...prev, ...Object.fromEntries(entries) }));
    };

    void loadStudies();

    return () => {
      isMounted = false;
    };
  }, [studyById, studyIdsToLoad]);

  const finalDecisionStudies = useMemo<FinalDecisionStudyItem[]>(() => {
    const totalAnnotators = groupedByUser.length;
    const shortNameById = new Map(
      groupedByUser.flatMap((group) => group.studies.map((study) => [study.studyId, study.studyShortName] as const))
    );

    return (
      studyIdsToLoad
        .map((studyId) => {
          const selectedBy = groupedByUser
            .filter((group) => group.studies.some((studyRef) => studyRef.studyId === studyId))
            .map((group) => group.userName)
            .sort((a, b) => a.localeCompare(b));

          return {
            studyId,
            shortName: shortNameById.get(studyId) ?? `Study ${studyId}`,
            study: studyById[studyId],
            selectedBy,
            isUnanimous: totalAnnotators > 0 && selectedBy.length === totalAnnotators,
          };
        })
        // By the names in the annotations, so the rows keep their order when the studies arrive.
        .sort((a, b) => a.shortName.localeCompare(b.shortName))
    );
  }, [groupedByUser, studyById, studyIdsToLoad]);

  const toggleFinalStudySelection = (studyId: number) => {
    setSelectedFinalStudyIds((prev) => {
      const next = new Set(prev);
      if (!next.delete(studyId)) {
        next.add(studyId);
      }
      return next;
    });
  };

  const handleDeleteReport = async () => {
    if (!reportIdParam || isDeletingReport) {
      return;
    }

    setIsDeletingReport(true);
    setDeleteReportError(null);
    try {
      await deleteReportById(Number(reportIdParam));

      setIsDeleteDialogOpen(false);
      reportFinished();

      if (projectIdParam) {
        navigate(curationPaths.review(projectIdParam));
      } else {
        navigate(curationPaths.overview);
      }
    } catch (error) {
      console.error("Failed to delete report:", error);
      setDeleteReportError("Unable to delete report. Please try again.");
    } finally {
      setIsDeletingReport(false);
    }
  };

  // The report goes into the core database with the selected studies and leaves the review; the next one opens.
  const handleMerge = async () => {
    if (!reportIdParam || isMerging) {
      return;
    }

    setIsMerging(true);
    setMergeError(null);
    try {
      await mergeReport(Number(reportIdParam), selectedStudyIdList);
      reportFinished();
      navigate(projectIdParam ? curationPaths.review(projectIdParam) : curationPaths.overview);
    } catch (error) {
      console.error("Failed to merge report:", error);
      const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setMergeError(typeof detail === "string" ? detail : "Unable to merge the report. Please try again.");
    } finally {
      setIsMerging(false);
    }
  };

  if (!reportIdParam) {
    return null;
  }

  // Merge shows while a study is selected; what holds it back, or why it failed, is said above it.
  const canMerge = selectedFinalStudyIds.size > 0;
  const mergeNote = mergeError ?? mergeBlock;

  return (
    // Room at the bottom for the floating actions (merge, delete).
    <div className="space-y-4 pb-20">
      {reportFlags.length > 0 ? (
        <Widget title="Report flags" icon={Flag} count={reportFlags.length}>
          <p className="-mt-1 mb-4 text-sm text-muted-foreground">
            Flags raised by annotators that may influence your final decision.
          </p>

          <div className="space-y-2">
            {reportFlags.map((flag) => (
              <div
                key={`report-flag-${flag}`}
                className="flex items-start gap-2 rounded-xl bg-primary/10 px-3 py-2"
              >
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <p className="text-sm font-medium text-primary">{flag}</p>
              </div>
            ))}
          </div>
        </Widget>
      ) : null}

      <Widget
        title="Final selection"
        icon={CircleCheckBig}
        count={finalDecisionStudies.length > 0 ? `${selectedFinalStudyIds.size} of ${finalDecisionStudies.length}` : undefined}
        actions={
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setSelectedFinalStudyIds(new Set())}
            disabled={selectedFinalStudyIds.size === 0 || isDeletingReport}
          >
            Clear
          </Button>
        }
      >
        <p className="-mt-1 mb-4 text-sm text-muted-foreground">
          Select one or more studies from the annotator suggestions, then merge the report into the database.
        </p>

        {groupedByUser.length === 0 ? (
          <Empty className="border">
            <EmptyHeader>
              <EmptyTitle>No annotations found</EmptyTitle>
              <EmptyDescription>
                This report does not have annotation assignments yet.
              </EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : finalDecisionStudies.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border/70 bg-background/60 p-4 text-sm text-muted-foreground">
            No study suggestions available yet.
          </div>
        ) : (
          <div className="space-y-3">
            {finalDecisionStudies.map((item) => {
              const { study } = item;
              const isSelected = selectedFinalStudyIds.has(item.studyId);
              const studyTimestamp = toTimestamp(study?.createdAt);
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
                  key={item.studyId}
                  role="button"
                  tabIndex={0}
                  aria-pressed={isSelected}
                  aria-label={isSelected ? `Deselect ${item.shortName}` : `Select ${item.shortName}`}
                  onClick={() => toggleFinalStudySelection(item.studyId)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      toggleFinalStudySelection(item.studyId);
                    }
                  }}
                  className={`p-4 bg-card rounded-xl relative w-full max-w-full overflow-hidden transition-colors duration-200 border flex items-center gap-4 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer ${rowClass}`}
                >
                  <div className="flex flex-col gap-3 flex-1 min-w-0">
                    <div className="flex h-6 items-center gap-3">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <h4 className="min-w-0 flex-1 truncate text-base font-semibold leading-6">
                            {study?.shortName ?? item.shortName}
                          </h4>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p>{study?.shortName ?? item.shortName}</p>
                        </TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 shrink-0 text-muted-foreground hover:bg-transparent hover:text-black"
                            aria-label={`Open details for ${item.shortName}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              openWithStudyId(item.studyId);
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

                    {/* One line of a fixed height: the study's details (and its graph, loaded after it) fill it
                        when they arrive, so the row keeps its size. */}
                    <div className="flex h-4 w-full min-w-0 items-center gap-x-4 overflow-hidden whitespace-nowrap text-xs">
                      {study === undefined ? (
                        <>
                          <Skeleton className="h-3 w-28" />
                          <Skeleton className="h-3 w-24" />
                          <Skeleton className="h-3 w-48" />
                        </>
                      ) : study === null ? (
                        <span className="text-muted-foreground/70">The details of this study could not be loaded.</span>
                      ) : (
                        <>
                          <div className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
                            <Users className="h-3 w-3" />
                            <span>{formatParticipantCount(study.numberParticipants)} participants</span>
                          </div>

                          <div className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
                            <Calendar className={`h-3 w-3 ${study.duration ? "" : "text-muted-foreground/50"}`} />
                            <span className={study.duration ? "" : "text-muted-foreground/50"}>
                              {study.duration || "No duration"}
                            </span>
                          </div>

                          <StudyCardGraph studyId={item.studyId} />
                        </>
                      )}
                    </div>

                    <div className="border-t border-border/60 pt-2">
                      {item.isUnanimous ? (
                        <div className="flex h-4 items-center gap-1.5 text-xs font-medium text-emerald-700">
                          {shouldShowNewHint ? (
                            <span className="mr-2 inline-flex items-center gap-1.5 text-amber-700">
                              <TriangleAlert className="h-3.5 w-3.5" />
                              <span className="italic">new</span>
                            </span>
                          ) : null}
                          <CircleCheckBig className="h-3.5 w-3.5" />
                          <span>Consensus (all annotators selected this study)</span>
                        </div>
                      ) : (
                        <div
                          className="flex min-h-4 items-center gap-1.5 text-xs font-medium"
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
                </div>
              );
            })}
          </div>
        )}

        {/* What the extensions review before the merge (e.g. the changes proposed to the selected studies). */}
        {reviewPanels.map((Panel, index) => (
          <div key={index} className="mt-4">
            <Panel reportId={Number(reportIdParam)} studyIds={selectedStudyIdList} onMergeBlock={blockMerge[index]} />
          </div>
        ))}

      </Widget>

      {/* The final actions float at the bottom right, into the body: the column the page is in may clip a fixed
          element. Delete stays in the corner; merge slides in next to it while a study is selected. */}
      {createPortal(
        <div className="fixed right-6 bottom-6 z-40 flex items-end gap-3" data-layout-part="review-actions">
          <div
            className={`relative transition-all duration-300 ease-out ${
              canMerge ? "translate-y-0 scale-100 opacity-100" : "pointer-events-none translate-y-4 scale-95 opacity-0"
            }`}
            aria-hidden={!canMerge}
            inert={!canMerge}
          >
            {mergeNote ? (
              <p
                className={`absolute right-0 bottom-full mb-2 w-max max-w-xs rounded-full px-3 py-1 text-xs shadow-md ${
                  mergeError
                    ? "bg-destructive text-white"
                    : "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
                }`}
              >
                {mergeNote}
              </p>
            ) : null}
            <Button
              type="button"
              size="lg"
              className="h-12 gap-2 rounded-full px-5 shadow-lg"
              onClick={() => void handleMerge()}
              disabled={isMerging || isDeletingReport || mergeBlock !== null}
            >
              <GitMerge className="h-4 w-4" />
              {isMerging
                ? "Merging..."
                : `Merge into database${selectedFinalStudyIds.size > 1 ? ` (${selectedFinalStudyIds.size} studies)` : ""}`}
            </Button>
          </div>

          <AlertDialog
            open={isDeleteDialogOpen}
            onOpenChange={(nextOpen) => {
              setIsDeleteDialogOpen(nextOpen);
              if (!nextOpen) {
                setDeleteReportError(null);
              }
            }}
          >
            <Tooltip>
              <TooltipTrigger asChild>
                <AlertDialogTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    aria-label="Delete report"
                    className="h-12 w-12 rounded-full bg-background text-destructive shadow-lg hover:bg-destructive/10 hover:text-destructive"
                    disabled={isDeletingReport || isMerging}
                  >
                    <Trash2 className="h-5 w-5" />
                  </Button>
                </AlertDialogTrigger>
              </TooltipTrigger>
              <TooltipContent>
                <p>Delete report</p>
              </TooltipContent>
            </Tooltip>
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
                  The report is removed from the update and kept in the archive only; it is not added to the database.
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
        </div>,
        document.body,
      )}
    </div>
  );
}
