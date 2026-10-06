import { useEffect, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Info, CircleDashed } from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  StudyDto,
  TagCategorySchemaDto,
  TagDto,
} from "@/types/apiDTOs";
import { getPersonsForStudy } from "@/lib/api/studiesApi";
import { colorClasses, type ColorClasses } from "@/lib/colors";
import { iconByName } from "@/lib/icons";

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

// How the persons (the authors of the study), which are no tag category, are drawn.
const PERSONS_COLORS: ColorClasses = colorClasses("violet");

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
      <div className="space-y-4 px-4">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold flex items-center gap-2.5">
            <div className="p-1.5 rounded-md bg-muted">
              <Info className="h-4 w-4" />
            </div>
            Tags
          </h3>
        </div>
        <div className="space-y-4">
          {[...categories.map((category) => category.key), "persons"].map((category) => (
            <div key={category} className="space-y-2 px-1">
              <div className="flex items-center gap-3">
                <Skeleton className="h-6 w-6" />
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-12" />
              </div>
              <div className="space-y-2">
                {[...Array(2)].map((_, index) => (
                  <Skeleton
                    key={index}
                    className="h-4 w-full rounded-xl"
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const renderTagItems = (category: TagCategorySchemaDto) => {
    const { items, nextCursor, loadingMore } = tags[category.key];
    const colors = colorClasses(category.color);

    if (!items.length) {
      return (
        <div className="flex items-center gap-3 py-6 px-4 text-muted-foreground">
          <CircleDashed className="h-4 w-4 opacity-50" />
          <p className="text-sm">No {category.label.toLowerCase()} available</p>
        </div>
      );
    }

    return (
      <div className="space-y-2 py-3">
        {items.map((item) => (
          <div
            key={item.id}
            className={`p-3.5 rounded-md border-l-2 ${colors.border} ${colors.bg} transition-colors`}
          >
            <p className="text-foreground text-sm leading-relaxed">
              {item.keyword}
            </p>
          </div>
        ))}
        {nextCursor && (
          <div className="flex justify-center pt-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => onLoadMore(category.key)}
              disabled={loadingMore}
            >
              {loadingMore ? "Loading..." : "Load more"}
            </Button>
          </div>
        )}
      </div>
    );
  };

  const renderPersonItems = (items: string[], emptyMessage: string) => {
    if (!items.length) {
      return (
        <div className="flex items-center gap-3 py-6 px-4 text-muted-foreground">
          <CircleDashed className="h-4 w-4 opacity-50" />
          <p className="text-sm">{emptyMessage}</p>
        </div>
      );
    }

    return (
      <div className="space-y-2 py-3">
        {items.map((item, index) => (
          <div
            key={index}
            className={`p-3.5 rounded-md border-l-2 ${PERSONS_COLORS.border} ${PERSONS_COLORS.bg} transition-colors`}
          >
            <p className="text-foreground text-sm leading-relaxed">{item}</p>
          </div>
        ))}
      </div>
    );
  };

  const renderAccordionItem = (
    value: string,
    label: string,
    icon: string,
    color: string,
    count: number,
    children: ReactNode,
    hasMore = false
  ) => {
    const colors = colorClasses(color);
    const Icon = iconByName(icon);

    return (
      <AccordionItem
        key={value}
        value={value}
        className="border-b border-border/50 last:border-b-0"
      >
        <AccordionTrigger className="py-4 hover:no-underline hover:bg-muted/30 px-1 rounded-md transition-colors">
          <div className="flex items-center gap-3">
            <div className={`p-1.5 rounded-md ${colors.bg}`}>
              <Icon className={`h-4 w-4 ${colors.accent}`} />
            </div>
            <span className="text-sm font-medium">{label}</span>
            <Badge
              variant="secondary"
              className="ml-1 h-5 px-1.5 text-xs font-normal"
            >
              {hasMore ? `${count}+` : count}
            </Badge>
          </div>
        </AccordionTrigger>
        <AccordionContent className="pb-2 pt-0 px-1">{children}</AccordionContent>
      </AccordionItem>
    );
  };

  return (
    <div className="space-y-4 px-4">
      <div className="flex items-center justify-between">
        <h3 className="text-base font-semibold flex items-center gap-2.5">
          <div className="p-1.5 rounded-md bg-muted">
            <Info className="h-4 w-4" />
          </div>
          Tags
        </h3>
      </div>
      <div>
        {combinedError && (
          <div className="mb-4 px-1 text-sm text-destructive">
            {combinedError}
          </div>
        )}
        <Accordion
          type="multiple"
          defaultValue={[...categories.map((category) => category.key), "persons"]}
          className="w-full"
        >
          {categories.map((category) =>
            renderAccordionItem(
              category.key,
              category.label,
              category.icon,
              category.color,
              tags[category.key].items.length,
              renderTagItems(category),
              tags[category.key].nextCursor !== null
            )
          )}

          {renderAccordionItem(
            "persons",
            "Persons",
            "user-round",
            "violet",
            persons.length,
            renderPersonItems(persons, "No persons information available")
          )}
        </Accordion>
      </div>
    </div>
  );
}
