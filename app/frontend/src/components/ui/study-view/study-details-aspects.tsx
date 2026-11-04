import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  StudyDto,
  TagCategorySchemaDto,
  TagDto,
} from "@/types/apiDTOs";
import { getPersonsForStudy } from "@/lib/api/studiesApi";
import { DetailChips, DetailRow } from "@/components/ui/study-view/detail-row";

// The persons shown before "+N more".
const PERSONS_SHOWN = 6;

// A paginated aspect list's current state, as owned and fetched by the parent
// (StudyDetails, via GET /studies/{study_id} and this category's own
// /studies/{study_id}/{category} endpoint for "Load more").
export interface AspectPageState {
  items: TagDto[];
  nextCursor: string | null;
  loadingMore: boolean;
}

interface StudyAspectsProps {
  study: StudyDto;
  loading: boolean;
  error: string | null;
  // The tag categories of the study schema, in the order they are shown.
  categories: TagCategorySchemaDto[];
  // The tags of the study per category.
  tags: Record<string, AspectPageState>;
  onLoadMore: (category: string) => void;
}

export function StudyAspects({
  study,
  loading,
  error,
  categories,
  tags,
  onLoadMore,
}: StudyAspectsProps) {
  const [persons, setPersons] = useState<string[]>([]);
  const [personsLoading, setPersonsLoading] = useState(true);
  const [personsError, setPersonsError] = useState<string | null>(null);
  const [personsExpanded, setPersonsExpanded] = useState(false);

  useEffect(() => {
    if (!study) {
      setPersons([]);
      setPersonsLoading(false);
      setPersonsError(null);
      return;
    }

    let isMounted = true;
    const controller = new AbortController();

    const loadPersons = async () => {
      setPersonsLoading(true);
      setPersonsError(null);

      try {
        const personsResponse = await getPersonsForStudy(study.studyId, {
          signal: controller.signal,
        });
        if (!isMounted) return;
        setPersons(personsResponse ?? []);
      } catch (fetchError) {
        if (!isMounted) return;
        const message =
          fetchError instanceof Error
            ? fetchError.message
            : "Unable to load persons.";
        setPersonsError(message);
      } finally {
        if (isMounted) setPersonsLoading(false);
      }
    };

    void loadPersons();

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [study]);

  const isLoading = loading || personsLoading;
  const combinedError = error ?? personsError;

  if (isLoading) {
    return (
      <>
        {[...categories.map((category) => category.key), "persons"].map((category) => (
          <div key={category} className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-3 px-4 py-1.5 sm:grid-cols-[8rem_minmax(0,1fr)]">
            <Skeleton className="h-3 w-20" />
            <div className="flex flex-wrap gap-1">
              <Skeleton className="h-5 w-24 rounded-md" />
              <Skeleton className="h-5 w-16 rounded-md" />
            </div>
          </div>
        ))}
      </>
    );
  }

  const shownPersons = personsExpanded ? persons : persons.slice(0, PERSONS_SHOWN);

  return (
    <>
      {combinedError && <p className="px-4 py-1.5 text-sm text-destructive">{combinedError}</p>}
      {categories.map((category) => {
        const { items, nextCursor, loadingMore } = tags[category.key];
        if (items.length === 0) return null;
        return (
          <DetailRow key={category.key} icon={category.icon} label={category.label}>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <DetailChips values={items.map((item) => item.keyword)} />
              {nextCursor && (
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto p-0 text-xs text-muted-foreground"
                  onClick={() => onLoadMore(category.key)}
                  disabled={loadingMore}
                >
                  {loadingMore ? "Loading..." : "Show more"}
                </Button>
              )}
            </div>
          </DetailRow>
        );
      })}
      {persons.length > 0 && (
        <DetailRow icon="user-round" label="Persons">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <DetailChips values={shownPersons} />
            {persons.length > PERSONS_SHOWN && (
              <Button
                variant="link"
                size="sm"
                className="h-auto p-0 text-xs text-muted-foreground"
                onClick={() => setPersonsExpanded((expanded) => !expanded)}
              >
                {personsExpanded ? "Show fewer" : `+${persons.length - PERSONS_SHOWN} more`}
              </Button>
            )}
          </div>
        </DetailRow>
      )}
    </>
  );
}
