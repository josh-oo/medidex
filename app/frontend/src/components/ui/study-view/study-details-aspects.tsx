import { useEffect, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Activity,
  Stethoscope,
  Target,
  Syringe,
  Info,
  UserRound,
  Users,
  CircleDashed,
} from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  StudyDto,
  TagDto,
} from "@/types/apiDTOs";
import { getPersonsForStudy } from "@/lib/api/studiesApi";

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
  interventions: AspectPageState;
  conditions: AspectPageState;
  outcomes: AspectPageState;
  participants: AspectPageState;
  design: AspectPageState;
  onLoadMoreInterventions: () => void;
  onLoadMoreConditions: () => void;
  onLoadMoreOutcomes: () => void;
  onLoadMoreParticipants: () => void;
  onLoadMoreDesign: () => void;
}

const categoryConfig = {
  interventions: {
    icon: Syringe,
    label: "Interventions",
    accentClass: "text-emerald-600 dark:text-emerald-400",
    bgClass: "bg-emerald-50 dark:bg-emerald-950/30",
    borderClass: "border-l-emerald-500",
  },
  conditions: {
    icon: Stethoscope,
    label: "Conditions",
    accentClass: "text-blue-600 dark:text-blue-400",
    bgClass: "bg-blue-50 dark:bg-blue-950/30",
    borderClass: "border-l-blue-500",
  },
  outcomes: {
    icon: Target,
    label: "Outcomes",
    accentClass: "text-rose-600 dark:text-rose-400",
    bgClass: "bg-rose-50 dark:bg-rose-950/30",
    borderClass: "border-l-rose-500",
  },
  participants: {
    icon: Users,
    label: "Participants",
    accentClass: "text-sky-600 dark:text-sky-400",
    bgClass: "bg-sky-50 dark:bg-sky-950/30",
    borderClass: "border-l-sky-500",
  },
  design: {
    icon: Activity,
    label: "Study Design",
    accentClass: "text-amber-600 dark:text-amber-400",
    bgClass: "bg-amber-50 dark:bg-amber-950/30",
    borderClass: "border-l-amber-500",
  },
  persons: {
    icon: UserRound,
    label: "Persons",
    accentClass: "text-violet-600 dark:text-violet-400",
    bgClass: "bg-violet-50 dark:bg-violet-950/30",
    borderClass: "border-l-violet-500",
  },
};

type PagedCategory = Exclude<keyof typeof categoryConfig, "persons">;

export function StudyAspects({
  study,
  loading,
  error,
  interventions,
  conditions,
  outcomes,
  participants,
  design,
  onLoadMoreInterventions,
  onLoadMoreConditions,
  onLoadMoreOutcomes,
  onLoadMoreParticipants,
  onLoadMoreDesign,
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
            Study Details
          </h3>
        </div>
        <div className="space-y-4">
          {Object.keys(categoryConfig).map((category) => (
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

  const renderTagItems = (
    items: TagDto[],
    category: PagedCategory,
    emptyMessage: string,
    nextCursor: string | null,
    loadingMore: boolean,
    onLoadMore: () => void
  ) => {
    const config = categoryConfig[category];

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
        {items.map((item) => (
          <div
            key={item.id}
            className={`p-3.5 rounded-md border-l-2 ${config.borderClass} ${config.bgClass} transition-colors`}
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
              onClick={onLoadMore}
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
    const config = categoryConfig.persons;

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
            className={`p-3.5 rounded-md border-l-2 ${config.borderClass} ${config.bgClass} transition-colors`}
          >
            <p className="text-foreground text-sm leading-relaxed">{item}</p>
          </div>
        ))}
      </div>
    );
  };

  const renderAccordionItem = (
    value: string,
    category: keyof typeof categoryConfig,
    count: number,
    children: ReactNode,
    hasMore = false
  ) => {
    const config = categoryConfig[category];
    const Icon = config.icon;

    return (
      <AccordionItem
        value={value}
        className="border-b border-border/50 last:border-b-0"
      >
        <AccordionTrigger className="py-4 hover:no-underline hover:bg-muted/30 px-1 rounded-md transition-colors">
          <div className="flex items-center gap-3">
            <div className={`p-1.5 rounded-md ${config.bgClass}`}>
              <Icon className={`h-4 w-4 ${config.accentClass}`} />
            </div>
            <span className="text-sm font-medium">{config.label}</span>
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
          Study Details
        </h3>
      </div>
      <div>
        {combinedError && (
          <div className="mb-4 px-1 text-sm text-destructive">
            {combinedError}
          </div>
        )}
        <Accordion type="multiple" className="w-full">
          {renderAccordionItem(
            "interventions",
            "interventions",
            interventions.items.length,
            renderTagItems(
              interventions.items,
              "interventions",
              "No interventions available",
              interventions.nextCursor,
              interventions.loadingMore,
              onLoadMoreInterventions
            ),
            interventions.nextCursor !== null
          )}

          {renderAccordionItem(
            "conditions",
            "conditions",
            conditions.items.length,
            renderTagItems(
              conditions.items,
              "conditions",
              "No conditions available",
              conditions.nextCursor,
              conditions.loadingMore,
              onLoadMoreConditions
            ),
            conditions.nextCursor !== null
          )}

          {renderAccordionItem(
            "outcomes",
            "outcomes",
            outcomes.items.length,
            renderTagItems(
              outcomes.items,
              "outcomes",
              "No outcomes available",
              outcomes.nextCursor,
              outcomes.loadingMore,
              onLoadMoreOutcomes
            ),
            outcomes.nextCursor !== null
          )}

          {renderAccordionItem(
            "participants",
            "participants",
            participants.items.length,
            renderTagItems(
              participants.items,
              "participants",
              "No participant description available",
              participants.nextCursor,
              participants.loadingMore,
              onLoadMoreParticipants
            ),
            participants.nextCursor !== null
          )}

          {renderAccordionItem(
            "design",
            "design",
            design.items.length,
            renderTagItems(
              design.items,
              "design",
              "No design information available",
              design.nextCursor,
              design.loadingMore,
              onLoadMoreDesign
            ),
            design.nextCursor !== null
          )}

          {renderAccordionItem(
            "persons",
            "persons",
            persons.length,
            renderPersonItems(persons, "No persons information available")
          )}
        </Accordion>
      </div>
    </div>
  );
}
