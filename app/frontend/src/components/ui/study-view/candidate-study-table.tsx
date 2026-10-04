"use client";

import { useState, useMemo, useCallback, useEffect} from "react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  FileText,
  BookMarked,
  Search,
  Sparkles,
  X,
  Microscope,
} from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { StudyCard } from "./study-card";
import { AddStudyTriggerSlot } from "@/context/add-study-trigger-context";
import { AdvancedSearchDialog } from "./advanced-search-dialog";
import { LoadMoreStudiesButton } from "./load-more-studies-button";
import type { StudyCandidateDto, StudyDto, StudyBaseDto, Page } from "@/types/apiDTOs";
import { ReportBannerSlot, StudyBadgeSlot } from "@/context/study-report-slots-context";
import { useReportStore } from "@/hooks/use-report-store";
import { useDetailsSheet } from "@/context/details-sheet-context";
import { assignNewStudyToReportByReportId } from "@/lib/api/reportApi";
import { searchStudies } from "@/lib/api/studiesApi";
import { getSimilarStudiesByReportId } from "@/lib/api/reportApi";

interface CandidateStudyTableProps {
  reportId?: number;
  studies: StudyCandidateDto[];
  // Studies of reports in the database that this report cites by DOI - the section is
  // only shown when this is non-empty.
  referencedStudies?: StudyCandidateDto[];
  nextCursor?: string | null;
  isLoadingMore?: boolean;
  onLoadMore?: () => void;
}

// The backend rejects shorter queries.
const MIN_SEARCH_QUERY_LENGTH = 3;
// Page size for both the explicit search and its "Load more" pagination.
const SEARCH_PAGE_SIZE = 10;

// Only searches within a report carry a relevance.
type SearchResult = StudyDto | StudyCandidateDto;

// Within a report the search runs through its similar-studies endpoint, so results carry
// their relevance for it; without one it is the plain study search.
const searchStudiesForReport = (
  reportId: number | undefined,
  query: string,
  cursor?: string
): Promise<Page<SearchResult>> =>
  reportId !== undefined
    ? getSimilarStudiesByReportId(reportId, { q: query, limit: SEARCH_PAGE_SIZE, cursor })
    : searchStudies({ q: query, limit: SEARCH_PAGE_SIZE, cursor });

export function CandidateStudyTable({
  reportId,
  studies,
  referencedStudies = [],
  nextCursor = null,
  isLoadingMore = false,
  onLoadMore,
}: CandidateStudyTableProps) {

  const [searchQuery, setSearchQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [searchNextCursor, setSearchNextCursor] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isLoadingMoreSearch, setIsLoadingMoreSearch] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [isAdvancedSearch, setIsAdvancedSearch] = useState(false);

  const addAssignedStudy = useReportStore((state) => state.addAssignedStudy);
  const syncAssignedStudy = useReportStore((state) => state.syncAssignedStudy);
  const currentReport = useReportStore((state) =>
    reportId !== undefined ? state.reports[reportId] : undefined
  );

  const {openWithStudyItem } = useDetailsSheet()

  const handleAssignStudy = useCallback(
    async (study: StudyDto) => {
      if (reportId === undefined) {
        return;
      }

      try {
        await addAssignedStudy(reportId, study);
        toast.success("Report assigned to study");
      } catch (error) {
        toast.error(
          `Failed to link study: ${
            error instanceof Error ? error.message : "Unknown error"
          }`
        );
        throw error;
      }
    },
    [reportId, addAssignedStudy]
  );

  const handleSaveNewStudy = useCallback(
    async (payload: StudyBaseDto) => {
      if (reportId === undefined) {
        throw new Error("Select a report before adding a new study.");
      }

      let createdStudy: StudyDto | null = null;
      try {
        createdStudy = (await assignNewStudyToReportByReportId(
          reportId,
          payload as unknown as StudyDto
        )) as unknown as StudyDto;
      } catch (error) {
        throw new Error("Failed to create study.");
      }

      if (!createdStudy || typeof createdStudy.studyId !== "number") {
        throw new Error("Invalid study response payload.");
      }

      syncAssignedStudy(reportId, createdStudy);
    },
    [reportId, syncAssignedStudy]
  );

  const candidateStudies = useMemo(
    () => [...studies].sort((a, b) => b.relevance - a.relevance),
    [studies]
  );

  // The single source of truth for assignment state - currentReport.assignedStudies already
  // updates reactively the moment addAssignedStudy/syncAssignedStudy touch the store, so
  // there's no separate local flag to keep in sync.
  const assignedStudyIds = useMemo(
    () => new Set((currentReport?.assignedStudies ?? []).map((assigned) => assigned.studyId)),
    [currentReport?.assignedStudies]
  );

  // The backend tells plain from advanced queries by the query itself; `advanced` only
  // drives how the results header displays it.
  const runSearch = useCallback(async (query: string, advanced: boolean = false) => {
    setIsSearching(true);
    setSearchError(null);
    setSubmittedQuery(query);
    setIsAdvancedSearch(advanced);

    try {
      const response = await searchStudiesForReport(reportId, query);
      setSearchResults(response.items);
      setSearchNextCursor(response.nextCursor);
    } catch (error) {
      setSearchResults(null);
      setSearchNextCursor(null);
      setSearchError(
        error instanceof Error ? error.message : "Failed to search studies."
      );
    } finally {
      setIsSearching(false);
    }
  }, [reportId]);

  const handleLoadMoreSearch = useCallback(() => {
    if (!searchNextCursor || isLoadingMoreSearch) {
      return;
    }

    setIsLoadingMoreSearch(true);
    searchStudiesForReport(reportId, submittedQuery, searchNextCursor)
      .then((response) => {
        setSearchResults((prev) => [...(prev ?? []), ...response.items]);
        setSearchNextCursor(response.nextCursor);
      })
      .catch((error) => {
        toast.error(
          `Failed to load more studies: ${
            error instanceof Error ? error.message : "Unknown error"
          }`
        );
      })
      .finally(() => {
        setIsLoadingMoreSearch(false);
      });
  }, [submittedQuery, reportId, searchNextCursor, isLoadingMoreSearch]);

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

  const handleAdvancedSearch = useCallback(
    (query: string) => {
      // Deliberately doesn't touch searchQuery (the plain-text input's bound value):
      // the raw grammar string (quotes/parens/==) isn't meant to be shown or re-submitted
      // there - the free-text form's Enter-to-submit always runs a plain ILIKE search,
      // which would silently break on this text. The advanced query itself is still
      // shown to the user via submittedQuery/isAdvancedSearch in the results header below.
      setSearchQuery("");
      void runSearch(query, true);
    },
    [runSearch]
  );

  const clearSearch = useCallback(() => {
    setSearchQuery("");
    setSubmittedQuery("");
    setSearchResults(null);
    setSearchNextCursor(null);
    setSearchError(null);
    setIsAdvancedSearch(false);
  }, []);

  // Prefill the explicit search with the report's trial id - the confirmed one if a
  // reviewer has set it, otherwise the unconfirmed .ris-upload/fulltext guess - so a
  // trial-registered study surfaces at the top immediately instead of the researcher
  // having to find and retype the id themselves. Re-runs whenever the selected report
  // (or its trial id, once it's loaded) changes; clears the search for reports with no
  // trial id of either kind.
  useEffect(() => {
    const trialId = currentReport?.trialId ?? currentReport?.preliminaryTrialId ?? null;
    if (trialId && trialId.trim().length >= MIN_SEARCH_QUERY_LENGTH) {
      setSearchQuery(trialId);
      void runSearch(trialId);
    } else {
      clearSearch();
    }
  }, [reportId, currentReport?.trialId, currentReport?.preliminaryTrialId, runSearch, clearSearch]);

  const handleStudyClick = (study: StudyDto) => {
    openWithStudyItem(study)
  };

  return (
    <div className="h-full flex flex-col pt-5">

      {/* Header - Sticky */}
      <div className="px-4 pb-4 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <Microscope className="h-6 w-6 text-primary" />
            </div>
            <h2 className="text-lg font-semibold">Relevant Studies</h2>
          </div>
          <div className="flex items-center gap-2">
              <AddStudyTriggerSlot
                currentReportId={reportId}
                onSaveStudy={handleSaveNewStudy}
              />
          </div>
        </div>

        {/* Global search across all studies */}
        <div className="mt-3">
          <form onSubmit={handleSearchSubmit} className="flex items-center gap-2">
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
            <AdvancedSearchDialog onSearch={handleAdvancedSearch} />
          </form>
          {searchError && (
            <p className="mt-1.5 text-xs text-destructive">{searchError}</p>
          )}
        </div>
      </div>

      <ReportBannerSlot reportId={reportId} />

      {/* Scrollable Content */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4">
        <div className="pt-3 pb-4 space-y-6">

          {/* Globally searched studies */}
          {searchResults && (
            <div>
              <div className="flex items-center gap-2 pb-2">
                <Search className="h-4 w-4 text-muted-foreground" />
                {isAdvancedSearch ? (
                  <h3 className="text-sm font-semibold flex items-center gap-2 min-w-0">
                    <span>Advanced search results for</span>
                    <code className="text-xs font-normal bg-muted px-1.5 py-0.5 rounded truncate">
                      {submittedQuery}
                    </code>
                  </h3>
                ) : (
                  <h3 className="text-sm font-semibold">
                    Search results for &ldquo;{submittedQuery}&rdquo;
                  </h3>
                )}
                <Badge variant="secondary" className="text-xs font-normal shrink-0">
                  {searchNextCursor ? `${searchResults.length}+` : searchResults.length}
                </Badge>
              </div>

              {searchResults.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-muted-foreground border border-dashed border-border rounded-lg">
                  <p className="text-sm font-medium">No matching studies</p>
                  <p className="text-xs mt-1">Try a different search query</p>
                </div>
              ) : (
                <>
                  {searchResults.map((study) => (
                    <StudyCard
                      key={`search-${study.studyId}`}
                      {...study}
                      isAssigned={assignedStudyIds.has(study.studyId)}
                      onClick={handleStudyClick}
                      onAssign={(target) => void handleAssignStudy(target)}
                    />
                  ))}
                  {searchNextCursor && (
                    <LoadMoreStudiesButton onClick={handleLoadMoreSearch} loading={isLoadingMoreSearch} />
                  )}
                </>
              )}

              <div className="pt-4 border-b border-border" />
            </div>
          )}

          {/* Studies of reports this report cites by DOI */}
          {referencedStudies.length > 0 && (
            <div>
              <div className="flex items-center gap-2 pb-2">
                <BookMarked className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">Referenced studies</h3>
                <Badge variant="secondary" className="text-xs font-normal">
                  {referencedStudies.length}
                </Badge>
              </div>
              {referencedStudies.map((study) => (
                <StudyCard
                  key={`referenced-${study.studyId}`}
                  {...study}
                  isAssigned={assignedStudyIds.has(study.studyId)}
                  onClick={handleStudyClick}
                  onAssign={(target) => void handleAssignStudy(target)}
                />
              ))}
              <div className="pt-4 border-b border-border" />
            </div>
          )}

          {/* Similar studies */}
          <div>
            {(searchResults || referencedStudies.length > 0) && (
              <div className="flex items-center gap-2 pb-2">
                <Sparkles className="h-4 w-4 text-muted-foreground" />
                <h3 className="text-sm font-semibold">Similar studies</h3>
                <Badge variant="secondary" className="text-xs font-normal">
                  {nextCursor ? `${candidateStudies.length}+` : candidateStudies.length}
                </Badge>
              </div>
            )}

            {candidateStudies.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <div className="p-3 rounded-full bg-muted mb-4">
                  <FileText className="h-6 w-6 opacity-50" />
                </div>
                <p className="text-sm font-medium">No studies found</p>
                <p className="text-xs mt-1">No relevant studies available</p>
              </div>
            ) : (
              <>
                {candidateStudies.map((study) => (
                  <StudyCard
                    key={study.studyId}
                    {...study}
                    isAssigned={assignedStudyIds.has(study.studyId)}
                    onClick={handleStudyClick}
                    onAssign={(target) => void handleAssignStudy(target)}
                    badge={<StudyBadgeSlot reportId={reportId} study={study} />}
                  />
                ))}

                {/* Load More Button */}
                {nextCursor && (
                  <LoadMoreStudiesButton onClick={onLoadMore} loading={isLoadingMore} />
                )}
              </>
            )}
          </div>
        </div>
      </div>

    </div>
  );
}
