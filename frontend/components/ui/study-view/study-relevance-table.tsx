"use client";

import { useState, useMemo, useEffect, useCallback} from "react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import type { RelevanceStudy } from "@/types/reports";
import {
  FileText,
  Search,
  Sparkles,
  X,
  Microscope,
} from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { StudyCard } from "./study-card";
import { AddStudyDialog } from "./add-study-dialog";
import { AIMatchSettingsDialog } from "./ai-match-settings-dialog";
import { LoadMoreStudiesButton } from "./load-more-studies-button";
import { useGenAIEvaluationStore } from "@/hooks/use-genai-evaluation-store";
import type { NewStudySuggestion, StudyDto, StudyCreateDto } from "@/types/apiDTOs";
import { StudyAIBadge } from "./study-ai-badge";
import { StudyAIReasonDialog } from "./study-ai-reason-dialog";
import { AiEvaluationProgress } from "./ai-evaluation-progress";
import { AiEvaluationHistoryDialog } from "./ai-evaluation-history-dialog";
import { useReportStore } from "@/hooks/use-report-store";
import { useDetailsSheet } from "@/app/context/details-sheet-context";

interface StudyRelevanceTableProps {
  reportId?: number;
  studies: RelevanceStudy[];
}

// The backend rejects shorter queries.
const MIN_SEARCH_QUERY_LENGTH = 3;
// The search endpoint is unbounded, so only the top hits are rendered.
const MAX_VISIBLE_SEARCH_RESULTS = 25;

export function StudyRelevanceTable({
  reportId,
  studies,
}: StudyRelevanceTableProps) {

  const [resolvedStudies, setResolvedStudies] = useState<RelevanceStudy[]>(() => [...studies]);
  const [searchQuery, setSearchQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [searchResults, setSearchResults] = useState<StudyDto[] | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const addAssignedStudies = useReportStore((state) => state.addAssignedStudy);
  const syncAssignedStudy = useReportStore((state) => state.syncAssignedStudy);
  const removeAssignedStudies = useReportStore((state) => state.removeAssignedStudy);
  const currentReport = useReportStore((state) =>
    reportId !== undefined ? state.reports[reportId] : undefined
  );

  const {openWithStudyItem } = useDetailsSheet()

  const results = useGenAIEvaluationStore((state) => state.results);
  const evaluationsByReport = useGenAIEvaluationStore((state) => state.evaluationsByReport);
  const runningEvaluations = useGenAIEvaluationStore((state) => state.runningEvaluations);
  const getStudyResult = useGenAIEvaluationStore((state) => state.getStudyResult);
  const dismissSuggestion = useGenAIEvaluationStore((state) => state.dismissSuggestion);

  const evalState = reportId ? evaluationsByReport[reportId] || null : null;
  const isRunning = reportId ? runningEvaluations.includes(reportId) : false;
  const studyResults = reportId ? results[reportId] : undefined;

  const [reasonDialogOpen, setReasonDialogOpen] = useState(false);
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false);
  const [selectedAIStudy, setSelectedAIStudy] = useState<{
    studyId: number;
    studyName: string;
  } | null>(null);
  // Extracted AI dialog state and methods

  //const wasAddStudyDialogOpen = useRef(false);
  const [progressCollapsedByReport, setProgressCollapsedByReport] = useState<Record<string, boolean>>({});
  const [aiDialogOpen, setAiDialogOpen] = useState(false);

  const summaryEvent = useMemo(
    () =>
      evalState?.streamMessages
        ? [...evalState.streamMessages]
          .reverse()
          .find((event) => event.node === "summarize_evaluation")
        : undefined,
    [evalState?.streamMessages]
  );
  const suggestionEvent = useMemo(
    () =>
      evalState?.streamMessages
        ? [...evalState.streamMessages]
          .reverse()
          .find((event) => event.node === "suggest_new_study")
        : undefined,
    [evalState?.streamMessages]
  );
  const newStudySuggestion: NewStudySuggestion | undefined =
    suggestionEvent?.details?.new_study ? suggestionEvent.details.new_study : undefined;


  const suggestionKey = newStudySuggestion
    ? `${reportId}:${JSON.stringify(newStudySuggestion)}`
    : null;

  const markStudyLinkedState = useCallback((studyId: number, linked: boolean) => {
    setResolvedStudies((prev) =>
      prev.map((entry) =>
        entry.study.studyId === studyId ? { ...entry, isLinked: linked } : entry
      )
    );
  }, []);

  const handleLinkedChange = useCallback(
    async (study: StudyDto, checked: boolean) => {
      if (reportId === undefined) {
        return;
      }

      if (checked) {
        try {
          await addAssignedStudies(reportId, study);
          markStudyLinkedState(study.studyId, true);
          toast.success("Report assigned to study");
        } catch (error) {
          toast.error(
            `Failed to link study: ${
              error instanceof Error ? error.message : "Unknown error"
            }`
          );
          throw error;
        }
      } else {
        try {
          await removeAssignedStudies(reportId, study.studyId);
          markStudyLinkedState(study.studyId, false);
          toast.success("Report unassigned from study");
        } catch (error) {
          toast.error(
            `Failed to unlink study: ${
              error instanceof Error ? error.message : "Unknown error"
            }`
          );
          throw error;
        }
      }
    },
    [
      reportId,
      addAssignedStudies,
      removeAssignedStudies,
      markStudyLinkedState,
    ]
  );

  const handleSaveNewStudy = useCallback(
    async (payload: StudyCreateDto) => {
      if (reportId === undefined) {
        throw new Error("Select a report before adding a new study.");
      }

      const response = await fetch(`/api/meerkat/reports/${reportId}/studies`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
        cache: "no-store",
      });

      let responseBody: unknown = null;
      const contentType = response.headers.get("Content-Type") ?? "";
      if (contentType.includes("application/json")) {
        try {
          responseBody = await response.json();
        } catch (error) {
          console.error("Failed to parse new study response payload", error);
        }
      }

      if (!response.ok) {
        const errorMessage =
          responseBody &&
          typeof responseBody === "object" &&
          responseBody !== null &&
          "error" in responseBody &&
          typeof (responseBody as { error?: string }).error === "string"
            ? (responseBody as { error: string }).error
            : "Failed to create study.";
        throw new Error(errorMessage);
      }

      const createdStudy =
        responseBody && typeof responseBody === "object"
          ? (responseBody as StudyDto)
          : null;

      if (!createdStudy || typeof createdStudy.studyId !== "number") {
        throw new Error("Invalid study response payload.");
      }

      syncAssignedStudy(reportId, createdStudy);
      markStudyLinkedState(createdStudy.studyId, true);

      if (suggestionKey) {
        dismissSuggestion(suggestionKey);
      }
    },
    [reportId, suggestionKey, dismissSuggestion, syncAssignedStudy, markStudyLinkedState]
  );

  useEffect(() => {
    const assignedStudyIds = new Set(
      (currentReport?.assignedStudies ?? []).map((assigned) => assigned.studyId)
    );
    setResolvedStudies(
      studies.map((study) => ({
        ...study,
        isLinked: study.isLinked || assignedStudyIds.has(study.study.studyId),
      }))
    );
  }, [studies, currentReport?.assignedStudies]);

  // Reset evaluation state when report changes
  //useEffect(() => {
  //  closeAIDialog();
  //}, []);

  const recommendedStudies = useMemo(
    () => [...resolvedStudies].sort((a, b) => b.relevance - a.relevance),
    [resolvedStudies]
  );

  const recommendedStudyIds = useMemo(
    () => new Set(recommendedStudies.map((entry) => entry.study.studyId)),
    [recommendedStudies]
  );

  const linkedStudyIds = useMemo(() => {
    const ids = new Set(
      (currentReport?.assignedStudies ?? []).map((assigned) => assigned.studyId)
    );
    resolvedStudies.forEach((entry) => {
      if (entry.isLinked) {
        ids.add(entry.study.studyId);
      }
    });
    return ids;
  }, [currentReport?.assignedStudies, resolvedStudies]);

  const visibleSearchResults = useMemo(
    () => (searchResults ?? []).slice(0, MAX_VISIBLE_SEARCH_RESULTS),
    [searchResults]
  );

  const runSearch = useCallback(async (query: string) => {
    setIsSearching(true);
    setSearchError(null);
    setSubmittedQuery(query);

    try {
      const response = await fetch(
        `/api/meerkat/studies?q=${encodeURIComponent(query)}`,
        { cache: "no-store" }
      );

      if (!response.ok) {
        throw new Error("Failed to search studies.");
      }

      const results = (await response.json()) as StudyDto[];
      setSearchResults(Array.isArray(results) ? results : []);
    } catch (error) {
      setSearchResults(null);
      setSearchError(
        error instanceof Error ? error.message : "Failed to search studies."
      );
    } finally {
      setIsSearching(false);
    }
  }, []);

  const handleSearchSubmit = useCallback(
    (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();

      const query = searchQuery.trim();
      if (query.length < MIN_SEARCH_QUERY_LENGTH) {
        setSearchError(
          `Enter at least ${MIN_SEARCH_QUERY_LENGTH} characters to search.`
        );
        return;
      }

      void runSearch(query);
    },
    [searchQuery, runSearch]
  );

  const clearSearch = useCallback(() => {
    setSearchQuery("");
    setSubmittedQuery("");
    setSearchResults(null);
    setSearchError(null);
  }, []);

  const handleAIBadgeClick = (studyId: number, studyName: string) => {
    setSelectedAIStudy({ studyId, studyName });
    setReasonDialogOpen(true);
  };

  const handleStudyClick = (study: StudyDto) => {
    openWithStudyItem(study)
  };

  const progressMessage = evalState?.isStreaming
    ? (evalState?.currentMessage ||
       (evalState?.streamMessages && evalState.streamMessages.length > 0
         ? evalState.streamMessages[evalState.streamMessages.length - 1]?.message
         : null) ||
       null)
    : (summaryEvent?.message ||
       evalState?.currentMessage ||
       (evalState?.streamMessages && evalState.streamMessages.length > 0
         ? evalState.streamMessages[evalState.streamMessages.length - 1]?.message
         : null) ||
       null);

  const shouldShowProgress = (evalState?.isStreaming ?? false) || Boolean(progressMessage);

  return (
    <div className="h-full flex flex-col pt-5">

      <AIMatchSettingsDialog
        open={aiDialogOpen}
        onOpenChange={setAiDialogOpen}
        reportId={reportId}
        studies={recommendedStudies}
      />

      {/* Header - Sticky */}
      <div className="px-4 pb-4 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Microscope className="h-6 w-6 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">Relevant Studies</h2>
            <Badge variant="secondary" className="text-xs font-normal">
              {recommendedStudies.length}
            </Badge>
          </div>
          <div className="flex items-center gap-2">
              <AddStudyDialog
                currentReportId={reportId}
                suggestedValues={newStudySuggestion}
                onSaveStudy={handleSaveNewStudy}
              />
          </div>
        </div>

        {/* Global search across all studies */}
        <div className="mt-3">
          <form onSubmit={handleSearchSubmit}>
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search all studies by name, trial ID, intervention, author... (press Enter)"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setSearchError(null);
                }}
                className="pl-9 pr-8"
              />
              {isSearching ? (
                <Spinner className="absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              ) : (
                (searchQuery || searchResults) && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label="Clear search"
                    className="absolute right-1 top-1/2 -translate-y-1/2 h-6 w-6 p-0"
                    onClick={clearSearch}
                  >
                    <X className="h-3 w-3" />
                  </Button>
                )
              )}
            </div>
          </form>
          {searchError && (
            <p className="mt-1.5 text-xs text-destructive">{searchError}</p>
          )}
        </div>
      </div>

      {shouldShowProgress ? (
          <AiEvaluationProgress
            message={progressMessage}
            isStreaming={evalState?.isStreaming ?? false}
            hasSummary={Boolean(summaryEvent?.message)}
            collapsed={progressCollapsedByReport[reportId !== undefined ? String(reportId) : ""] ?? false}
            onCollapsedChange={(collapsed) => {
              if (reportId !== undefined) {
                setProgressCollapsedByReport(prev => ({ ...prev, [String(reportId)]: collapsed }));
              }
            }}
            onShowStepHistory={() => {
              setHistoryDialogOpen(true)
            }}
          />
      ) : null}

      {/* Scrollable Content */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4">
        <div className="pt-3 pb-4 space-y-6">

          {/* Globally searched studies */}
          {searchResults && (
            <div>
              <div className="flex items-center gap-2 pb-2">
                <Search className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">
                  Search results for &ldquo;{submittedQuery}&rdquo;
                </h3>
                <Badge variant="secondary" className="text-xs font-normal">
                  {searchResults.length}
                </Badge>
              </div>

              {searchResults.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-muted-foreground border border-dashed border-border rounded-lg">
                  <p className="text-sm font-medium">No matching studies</p>
                  <p className="text-xs mt-1">Try a different search query</p>
                </div>
              ) : (
                <>
                  {visibleSearchResults.map((study) => (
                    <StudyCard
                      key={`search-${study.studyId}`}
                      study={study}
                      isLinked={linkedStudyIds.has(study.studyId)}
                      alsoRecommended={recommendedStudyIds.has(study.studyId)}
                      onClick={handleStudyClick}
                      onLink={(target) => void handleLinkedChange(target, true)}
                    />
                  ))}
                  {searchResults.length > visibleSearchResults.length && (
                    <p className="pt-1 text-xs text-muted-foreground text-center">
                      Showing the top {visibleSearchResults.length} of{" "}
                      {searchResults.length} matches. Refine your query to narrow
                      them down.
                    </p>
                  )}
                </>
              )}

              <div className="pt-4 border-b border-border" />
            </div>
          )}

          {/* Recommended studies */}
          <div>
            {searchResults && (
              <div className="flex items-center gap-2 pb-2">
                <Sparkles className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">Recommended studies</h3>
                <Badge variant="secondary" className="text-xs font-normal">
                  {recommendedStudies.length}
                </Badge>
              </div>
            )}

            {recommendedStudies.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <div className="p-3 rounded-full bg-muted mb-4">
                  <FileText className="h-6 w-6 opacity-50" />
                </div>
                <p className="text-sm font-medium">No studies found</p>
                <p className="text-xs mt-1">No relevant studies available</p>
              </div>
            ) : (
              <>
                {recommendedStudies.map((entry) => (
                  <StudyCard
                    key={entry.study.studyId}
                    study={entry.study}
                    relevance={entry.relevance}
                    isLinked={linkedStudyIds.has(entry.study.studyId)}
                    onClick={handleStudyClick}
                    onLink={(target) => void handleLinkedChange(target, true)}
                    aiBadge={
                      studyResults?.[entry.study.studyId] && (
                        <StudyAIBadge
                          classification={studyResults[entry.study.studyId].classification}
                          onClick={(e) => {
                            e.stopPropagation();
                            handleAIBadgeClick(
                              entry.study.studyId,
                              entry.study.shortName
                            );
                          }}
                        />
                      )
                    }
                  />
                ))}

                {/* Load More Button */}
                <LoadMoreStudiesButton />
              </>
            )}
          </div>
        </div>
      </div>

      {/* AI Reason Dialog */}
      {selectedAIStudy && reportId !== undefined && (
        <StudyAIReasonDialog
          open={reasonDialogOpen}
          onOpenChange={setReasonDialogOpen}
          studyName={selectedAIStudy.studyName}
          classification={
            getStudyResult(
              reportId,
              selectedAIStudy.studyId
            )?.classification || "unsure"
          }
          reason={
            getStudyResult(
              reportId,
              selectedAIStudy.studyId
            )?.reason || "No reason available"
          }
        />
      )}

      <AiEvaluationHistoryDialog
        open={historyDialogOpen}
        onOpenChange={setHistoryDialogOpen}
        streamMessages={evalState?.streamMessages || []}
      />
    </div>
  );
}
