import { useState, useMemo, useCallback, useEffect} from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import {
  FileText,
  BookMarked,
  Plus,
  Search,
  Sparkles,
  X,
} from "lucide-react";
import { Spinner } from "@/components/ui/spinner";
import { StudyCard } from "./study-card";
import { StudyDetails } from "./study-details";
import { Widget } from "@/components/ui/widget";
import { AddStudyTriggerSlot } from "@/context/add-study-trigger-context";
import { AdvancedSearchDialog } from "./advanced-search-dialog";
import { Pager } from "@/components/ui/pager";
import { useClientPages } from "@/hooks/use-client-pages";
import { WorkbenchAside } from "@/context/workbench-aside-context";
import type { StudyCandidateDto, StudyDto, StudyBaseDto, Page } from "@/types/apiDTOs";
import { ReportBannerSlot, StudyBadgeSlot } from "@/context/study-report-slots-context";
import { useReportStore } from "@/hooks/use-report-store";
import { useExtensionRegistry, type StudyLinkReview } from "@/context/extension-registry-context";
import { assignNewStudyToReportByReportId } from "@/lib/api/reportApi";
import { searchStudies } from "@/lib/api/studiesApi";
import { onStudySearchRequest } from "@/lib/study-search-request";
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
// Page size for both the explicit search and its pages.
const SEARCH_PAGE_SIZE = 10;
// Similar studies shown per page.
const STUDY_PAGE_SIZE = 10;

// Without an extension reviewing links, every link goes ahead.
const useNoLinkReview = (): StudyLinkReview => ({ confirmLink: async () => true, dialog: null });

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

  // The card whose study details are folded out, by its section and study ("similar-12").
  const [expandedCard, setExpandedCard] = useState<string | null>(null);
  useEffect(() => {
    setExpandedCard(null);
  }, [reportId]);
  const { useStudyLinkReview = useNoLinkReview } = useExtensionRegistry();
  const linkReview = useStudyLinkReview();

  const handleAssignStudy = useCallback(
    async (study: StudyDto) => {
      if (reportId === undefined) {
        return;
      }

      try {
        if (!(await linkReview.confirmLink(reportId, study))) {
          return;
        }
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
    [reportId, addAssignedStudy, linkReview]
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

  // Searches requested from elsewhere in the UI (e.g. a clicked tag in a report abstract).
  useEffect(
    () =>
      onStudySearchRequest((query) => {
        const trimmed = query.trim();
        setSearchQuery(trimmed);
        if (trimmed.length >= MIN_SEARCH_QUERY_LENGTH) void runSearch(trimmed);
      }),
    [runSearch]
  );

  const renderStudyCard = (section: string, study: SearchResult) => {
    const cardKey = `${section}-${study.studyId}`;
    const expanded = expandedCard === cardKey;
    return (
      <StudyCard
        key={cardKey}
        {...study}
        isAssigned={assignedStudyIds.has(study.studyId)}
        expanded={expanded}
        details={expanded ? <StudyDetails study={study} isActive variant="inline" /> : null}
        onClick={() => setExpandedCard((current) => (current === cardKey ? null : cardKey))}
        onAssign={(target) => void handleAssignStudy(target)}
        badge={<StudyBadgeSlot reportId={reportId} study={study} />}
        reportId={reportId}
      />
    );
  };

  const similarPages = useClientPages({
    items: candidateStudies,
    pageSize: STUDY_PAGE_SIZE,
    hasMore: nextCursor !== null,
    loadMore: onLoadMore,
    resetKey: reportId,
  });
  const searchPages = useClientPages({
    items: searchResults ?? [],
    pageSize: SEARCH_PAGE_SIZE,
    hasMore: searchNextCursor !== null,
    loadMore: handleLoadMoreSearch,
    resetKey: `${reportId}-${submittedQuery}`,
  });

  return (
    // Room at the bottom for floating actions of extensions (e.g. a chat button).
    <div className="space-y-4 pb-20">
      <ReportBannerSlot reportId={reportId} />

      {/* Global search across all studies */}
      <Widget
        title="Find a study"
        icon={Search}
        count={searchResults && !searchPages.canPrev && !searchPages.canNext ? searchResults.length : undefined}
        actions={
          searchResults && (
            <Pager
              range={searchPages.range}
              canPrev={searchPages.canPrev}
              canNext={searchPages.canNext}
              onPrev={searchPages.prev}
              onNext={searchPages.next}
              loading={isLoadingMoreSearch}
            />
          )
        }
      >
        <form onSubmit={handleSearchSubmit} className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Name, trial ID, intervention, author... (press Enter)"
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setSearchError(null);
              }}
              className="pl-9 pr-8 bg-muted/60 border-transparent"
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

        {searchResults && (
          <div className="mt-4 space-y-2">
            {isAdvancedSearch ? (
              <p className="flex min-w-0 items-center gap-2 text-xs text-muted-foreground">
                <span className="shrink-0">Advanced search for</span>
                <code className="bg-muted px-1.5 py-0.5 rounded truncate">{submittedQuery}</code>
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Results for &ldquo;{submittedQuery}&rdquo;
              </p>
            )}

            {searchResults.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-muted-foreground rounded-xl bg-muted/50">
                <p className="text-sm font-medium">No matching studies</p>
                <p className="text-xs mt-1">Try a different search query</p>
              </div>
            ) : (
              searchPages.isTurning ? (
                <div className="flex justify-center py-10"><Spinner className="h-5 w-5 text-muted-foreground" /></div>
              ) : (
                searchPages.pageItems.map((study) => renderStudyCard("search", study))
              )
            )}
          </div>
        )}
      </Widget>

      {/* Studies of reports this report cites by DOI */}
      {referencedStudies.length > 0 && (
        <Widget title="Referenced studies" icon={BookMarked} count={referencedStudies.length}>
          <div className="space-y-2">
            {referencedStudies.map((study) => renderStudyCard("referenced", study))}
          </div>
        </Widget>
      )}

      {/* Similar studies */}
      <Widget
        title="Similar studies"
        icon={Sparkles}
        // The pager shows the count while there are pages.
        count={similarPages.canPrev || similarPages.canNext ? undefined : candidateStudies.length}
        actions={
          <Pager
            range={similarPages.range}
            canPrev={similarPages.canPrev}
            canNext={similarPages.canNext}
            onPrev={similarPages.prev}
            onNext={similarPages.next}
            loading={isLoadingMore}
          />
        }
      >
        {candidateStudies.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-muted-foreground">
            <div className="p-3 rounded-full bg-muted mb-3">
              <FileText className="h-6 w-6 opacity-50" />
            </div>
            <p className="text-sm font-medium">No studies found</p>
            <p className="text-xs mt-1">No relevant studies available</p>
          </div>
        ) : (
          <div className="space-y-2">
            {similarPages.isTurning
              ? <div className="flex justify-center py-10"><Spinner className="h-5 w-5 text-muted-foreground" /></div>
              : similarPages.pageItems.map((study) => renderStudyCard("similar", study))}
          </div>
        )}
      </Widget>

      {/* Only needed when none of the candidates above match */}
      <WorkbenchAside>
      <Widget title="Add new study" icon={Plus}>
        <p className="-mt-1 mb-4 text-sm text-muted-foreground">
          None of the suggested studies match? Link this report to a new study.
        </p>
        <AddStudyTriggerSlot
          currentReportId={reportId}
          extensions={currentReport?.extensions}
          onSaveStudy={handleSaveNewStudy}
          inline
        />
      </Widget>
      </WorkbenchAside>
      {linkReview.dialog}
    </div>
  );
}
