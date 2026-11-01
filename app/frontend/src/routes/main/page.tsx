import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ArrowRight, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { StudySearchBar } from "@/components/search/study-search-bar";
import { StudyResultCard } from "@/components/search/study-result-card";
import { StudyFilterPanel } from "@/components/search/study-filter-panel";
import { QuerySummary } from "@/components/search/query-summary";
import { DatabasePicker } from "@/components/search/database-picker";
import { useCuration } from "@/hooks/use-curation";
import { useAuthStore } from "@/hooks/use-auth";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { useTagCatalogs } from "@/hooks/use-tag-catalog";
import { parseDatabaseIds } from "@/lib/databases";
import { useStudySchema } from "@/hooks/use-study-schema";
import { searchStudies } from "@/lib/api/studiesApi";
import { PageLink } from "@/lib/page-transition";
import { curationPaths, projectSteps, taskSteps, waitingReports, type CurationStep } from "@/lib/curation-steps";
import {
  buildStudyQuery,
  filterFromParam,
  filterToParam,
  freeTextFields,
  sameFilter,
  type StudyFilter,
} from "@/lib/study-filters";
import { cn } from "@/lib/utils";
import type { StudyDto } from "@/types/apiDTOs";

const PAGE_SIZE = 20;
// The search endpoint needs a query of at least three characters.
const MIN_QUERY_LENGTH = 3;

// The search lives in the URL (?q=text&f=field:value&f=...&all=field&db=...), so it can be bookmarked, shared and
// gone back to.
function useSearchState() {
  const [params, setParams] = useSearchParams();
  const text = params.get("q") ?? "";
  const databaseParams = params.getAll("db").join("\n");
  const databases = useMemo(
    () => (databaseParams ? parseDatabaseIds(databaseParams.split("\n")) : []),
    [databaseParams]
  );
  const allParams = params.getAll("all").join("\n");
  const allFields = useMemo(() => (allParams ? allParams.split("\n") : []), [allParams]);
  const filterParams = params.getAll("f").join("\n");
  const filters = useMemo(
    () =>
      filterParams
        .split("\n")
        .map(filterFromParam)
        .filter((filter): filter is StudyFilter => filter !== null),
    [filterParams]
  );

  const update = useCallback(
    (
      nextText: string,
      nextFilters: StudyFilter[],
      nextDatabases: number[] = databases,
      nextAllFields: string[] = allFields
    ) => {
      const next = new URLSearchParams();
      if (nextText) next.set("q", nextText);
      nextFilters.forEach((filter) => next.append("f", filterToParam(filter)));
      // "All" only means something for a field with filters.
      nextAllFields
        .filter((field) => nextFilters.some((filter) => filter.field === field))
        .forEach((field) => next.append("all", field));
      nextDatabases.forEach((database) => next.append("db", String(database)));
      setParams(next);
    },
    [setParams, databases, allFields]
  );

  return {
    text,
    filters,
    databases,
    allFields,
    setDatabases: (nextDatabases: number[]) => update(text, filters, nextDatabases),
    toggleAll: (field: string) =>
      update(
        text,
        filters,
        databases,
        allFields.includes(field) ? allFields.filter((other) => other !== field) : [...allFields, field]
      ),
    // What is searched from the bar starts a new search; the filter column narrows the current one.
    searchText: (nextText: string) => update(nextText, []),
    searchFilter: (filter: StudyFilter) => update("", [filter]),
    addFilter: (filter: StudyFilter) =>
      update(text, filters.some((active) => sameFilter(active, filter)) ? filters : [...filters, filter]),
    removeFilter: (filter: StudyFilter) => update(text, filters.filter((active) => !sameFilter(active, filter))),
    clear: () => update("", []),
  };
}

export default function Home() {
  const {
    text,
    filters,
    databases,
    allFields,
    setDatabases,
    toggleAll,
    searchText,
    searchFilter,
    addFilter,
    removeFilter,
    clear,
  } = useSearchState();
  const { schema } = useStudySchema();
  const textFields = useMemo(() => freeTextFields(schema?.tags ?? []), [schema]);
  const searching = Boolean(text || filters.length);

  // One page in two states: the start page with the search in its middle and, once something is searched, the
  // search at the top with the results below. The bar stays the same element and moves between the two.
  return (
    <div className="flex-1 overflow-auto">
      <div
        className={cn(
          "mx-auto max-w-6xl px-4 pb-12 ease-out motion-safe:transition-[padding] motion-safe:duration-500 md:px-6",
          searching ? "pt-4 md:pt-6" : "pt-[16vh]"
        )}
      >
        <div
          aria-hidden={searching}
          className={cn(
            "grid ease-out motion-safe:transition-[grid-template-rows,opacity,margin] motion-safe:duration-500",
            searching ? "grid-rows-[0fr] opacity-0" : "mb-8 grid-rows-[1fr] opacity-100"
          )}
        >
          <div className="overflow-hidden text-center">
            <h1 className="text-3xl font-semibold tracking-tight">Search the study database</h1>
            <p className="mx-auto mt-3 max-w-lg text-[15px] text-muted-foreground">
              Every report is linked to the study it describes. Search by intervention, condition, outcome, trial
              ID or author.
            </p>
          </div>
        </div>

        <div
          className={cn(
            "mx-auto ease-out motion-safe:transition-[max-width] motion-safe:duration-500",
            searching ? "max-w-3xl" : "max-w-2xl"
          )}
        >
          <StudySearchBar
            text={text}
            onSearch={searchText}
            onAddFilter={searchFilter}
            onClear={searching ? clear : undefined}
            databases={databases}
            leading={
              <DatabasePicker selected={databases} onChange={setDatabases} size={searching ? "compact" : "hero"} />
            }
            size={searching ? "compact" : "hero"}
            autoFocus
          />
        </div>

        {searching ? (
          <Results
            query={buildStudyQuery(text, filters, textFields, allFields)}
            databases={databases}
            text={text}
            filters={filters}
            allFields={allFields}
            onToggleAll={toggleAll}
            onAddFilter={addFilter}
            onRemoveFilter={removeFilter}
          />
        ) : (
          <CurationHint />
        )}
      </div>
    </div>
  );
}

interface ResultsProps {
  query: string;
  /** The ids of the databases to search; empty means all of them. */
  databases: number[];
  text: string;
  filters: StudyFilter[];
  allFields: string[];
  onToggleAll: (field: string) => void;
  onAddFilter: (filter: StudyFilter) => void;
  onRemoveFilter: (filter: StudyFilter) => void;
}

// The filters and the results below the search; they fade in when the search starts.
function Results({
  query,
  databases,
  text,
  filters,
  allFields,
  onToggleAll,
  onAddFilter,
  onRemoveFilter,
}: ResultsProps) {
  const catalogs = useTagCatalogs(true, databases);
  const [results, setResults] = useState<StudyDto[] | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const tooShort = query.length < MIN_QUERY_LENGTH;

  useEffect(() => {
    setResults(null);
    setNextCursor(null);
    setError(null);
    setExpandedId(null);
    if (tooShort) return;

    let cancelled = false;
    setLoading(true);
    searchStudies({ q: query, limit: PAGE_SIZE, databases })
      .then((page) => {
        if (cancelled) return;
        setResults(page.items);
        setNextCursor(page.nextCursor);
      })
      .catch((searchError) => {
        if (!cancelled) setError(searchError instanceof Error ? searchError.message : "The search failed.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, databases, tooShort]);

  const loadMore = () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    searchStudies({ q: query, limit: PAGE_SIZE, cursor: nextCursor, databases })
      .then((page) => {
        setResults((previous) => [...(previous ?? []), ...page.items]);
        setNextCursor(page.nextCursor);
      })
      .catch((searchError) => console.error("Failed to load more studies:", searchError))
      .finally(() => setLoadingMore(false));
  };

  const terms = [text, ...filters.filter((filter) => filter.field !== "status").map((filter) => filter.value)];

  return (
    <div className="mt-6 motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-3 motion-safe:duration-500">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
        {/* A fixed column: its content (long chips) never pushes into the results. */}
        <aside aria-label="Filters" className="min-w-0 lg:sticky lg:top-4 lg:w-60 lg:max-w-60 lg:shrink-0">
          <Button
            variant="outline"
            size="sm"
            className="mb-3 gap-2 lg:hidden"
            aria-expanded={showFilters}
            onClick={() => setShowFilters((value) => !value)}
          >
            <SlidersHorizontal className="h-4 w-4" />
            Filters{filters.length > 0 && ` (${filters.length})`}
          </Button>
          <div className={showFilters ? "block" : "hidden lg:block"}>
            <StudyFilterPanel
              catalogs={catalogs}
              filters={filters}
              onAdd={onAddFilter}
              onRemove={onRemoveFilter}
            />
          </div>
        </aside>

        <main className="min-w-0 flex-1 space-y-3">
          {tooShort ? (
            <p className="text-sm text-muted-foreground">Type at least three characters.</p>
          ) : (
            <QuerySummary
              text={text}
              filters={filters}
              allFields={allFields}
              catalogs={catalogs}
              onToggleAll={onToggleAll}
              onRemove={onRemoveFilter}
            />
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}

          {loading ? (
            <div className="flex justify-center py-16">
              <Spinner className="h-6 w-6 text-muted-foreground" />
            </div>
          ) : results && results.length === 0 ? (
            <div className="rounded-2xl border border-dashed px-6 py-12 text-center">
              <p className="font-medium">No matching studies</p>
              <p className="mt-1 text-sm text-muted-foreground">Try other words or fewer filters.</p>
            </div>
          ) : (
            <>
              {results?.map((study) => (
                <StudyResultCard
                  key={study.studyId}
                  study={study}
                  terms={terms}
                  expanded={expandedId === study.studyId}
                  onToggle={() => setExpandedId((current) => (current === study.studyId ? null : study.studyId))}
                />
              ))}
              {nextCursor && (
                <div className="flex justify-center pt-2">
                  <Button variant="outline" onClick={loadMore} disabled={loadingMore}>
                    {loadingMore && <Spinner className="h-4 w-4" />}
                    Show more
                  </Button>
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

// The way to the database management going on in the background, with the open tasks there of the current user (a
// step of a project with reports waiting for them). The projects themselves are listed on that page.
function CurationHint() {
  const { loading, isAdmin, tasks, projects } = useCuration();
  // Fades in only when it had to wait for its data; known from before, it is there with the page.
  const [fadeIn] = useState(loading);
  const userId = useAuthStore((s) => s.user?.id);
  const { projectSteps: stepResolvers } = useExtensionRegistry();

  // Counts the updates with open steps, each once however many of its steps are waiting.
  const openTasks = useMemo(() => {
    const hasOpen = (steps: CurationStep[]) => steps.some((step) => waitingReports(step) > 0);
    const projectIds = new Set(projects.map((project) => project.projectId));
    return [
      ...projects.map((project) => {
        const role = {
          isOwner: Boolean(userId) && project.owner === userId,
          isAssignee: Boolean(userId) && (project.assignees ?? []).some((assignee) => assignee.userId === userId),
        };
        const extraSteps = stepResolvers
          .map((resolve) => resolve(project))
          .filter((step): step is CurationStep => step !== null);
        return hasOpen(projectSteps(project, role, extraSteps));
      }),
      // An admin's own tasks are among the projects already.
      ...tasks.filter((task) => !projectIds.has(task.projectId)).map((task) => hasOpen(taskSteps(task))),
    ].filter(Boolean).length;
  }, [projects, tasks, userId, stepResolvers]);

  // Only for the people who take part in the curation; admins can always start a project there.
  if (loading || (!isAdmin && tasks.length === 0)) return null;

  return (
    <div
      className={cn(
        "mt-8 flex flex-col items-center gap-2",
        fadeIn && "motion-safe:animate-in motion-safe:fade-in motion-safe:duration-500"
      )}
    >
      {openTasks > 0 && (
        <PageLink
          to={curationPaths.overview}
          className="group inline-flex max-w-full items-center gap-2.5 rounded-full border bg-card px-4 py-2 text-sm shadow-xs transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="h-2 w-2 shrink-0 rounded-full bg-primary" aria-hidden="true" />
          <span className="min-w-0 truncate font-medium">
            {openTasks} open {openTasks === 1 ? "task" : "tasks"}
          </span>
          <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
        </PageLink>
      )}
      <PageLink
        to={curationPaths.overview}
        className="rounded text-xs text-muted-foreground/80 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        Database management
      </PageLink>
    </div>
  );
}
