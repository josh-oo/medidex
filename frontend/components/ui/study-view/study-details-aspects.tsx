"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Activity,
  Stethoscope,
  Target,
  Syringe,
  Info,
  UserRound,
  CircleDashed,
} from "lucide-react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  ConditionDto,
  InterventionDto,
  OutcomeDto,
  StudyDto,
} from "@/types/apiDTOs";

interface StudyDetailsProps {
  study: StudyDto;
}

const categoryConfig = {
  interventions: {
    icon: Syringe,
    label: "Interventions",
    accentClass: "text-emerald-600 dark:text-emerald-400",
    bgClass: "bg-emerald-50 dark:bg-emerald-950/30",
    borderClass: "border-l-blue-500",
  },
  conditions: {
    icon: Stethoscope,
    label: "Conditions",
    accentClass: "text-blue-600 dark:text-blue-400",
    bgClass: "bg-blue-50 dark:bg-blue-950/30",
    borderClass: "border-l-rose-500",
  },
  outcomes: {
    icon: Target,
    label: "Outcomes",
    accentClass: "text-rose-600 dark:text-rose-400",
    bgClass: "bg-rose-50 dark:bg-rose-950/30",
    borderClass: "border-l-emerald-500",
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

type DescriptionItem = {
  id?: number;
  description?: string;
};

interface StudyAspectData {
  interventions: DescriptionItem[];
  conditions: DescriptionItem[];
  outcomes: DescriptionItem[];
  design: string[];
  persons: string[];
}

const defaultAspectData: StudyAspectData = {
  interventions: [],
  conditions: [],
  outcomes: [],
  design: [],
  persons: [],
};

const mapDescriptionItems = (
  items: Array<{ ID?: number; Description?: string }>
): DescriptionItem[] =>
  items.map((item, index) => ({
    id: item.ID ?? index,
    description: item.Description ?? "",
  }));

export function StudyAspects({ study }: StudyDetailsProps) {
  const [aspectData, setAspectData] = useState<StudyAspectData>(
    defaultAspectData
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { interventions, conditions, outcomes, design, persons } = aspectData;

  useEffect(() => {
    if (!study) {
      setAspectData(defaultAspectData);
      setLoading(false);
      setError(null);
      return;
    }

    let isMounted = true;
    const controller = new AbortController();
    const basePath = `/api/meerkat/studies/${study.studyId}`;

    async function fetchJson<T>(endpoint: string, label: string): Promise<T> {
      const response = await fetch(`${basePath}/${endpoint}`, {
        signal: controller.signal,
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Failed to load ${label}`);
      }

      return response.json() as Promise<T>;
    }

    const loadAspects = async () => {
      setLoading(true);
      setError(null);

      try {
        const [
          interventionsResponse,
          conditionsResponse,
          outcomesResponse,
          designResponse,
          personsResponse,
        ] = await Promise.all([
          fetchJson<InterventionDto[]>(
            "interventions",
            "intervention information"
          ),
          fetchJson<ConditionDto[]>(
            "conditions",
            "condition information"
          ),
          fetchJson<OutcomeDto[]>("outcomes", "outcome information"),
          fetchJson<string[]>("design", "design information"),
          fetchJson<string[]>("persons", "persons information"),
        ]);

        if (!isMounted) {
          return;
        }

        setAspectData({
          interventions: mapDescriptionItems(interventionsResponse),
          conditions: mapDescriptionItems(conditionsResponse),
          outcomes: mapDescriptionItems(outcomesResponse),
          design: designResponse ?? [],
          persons: personsResponse ?? [],
        });
      } catch (fetchError) {
        if (!isMounted) {
          return;
        }

        const message =
          fetchError instanceof Error
            ? fetchError.message
            : "Unable to load study details.";
        setError(message);
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    void loadAspects();

    return () => {
      isMounted = false;
      controller.abort();
    };
  }, [study]);

  if (loading) {
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

  const renderCategoryItems = (
    items: Array<{ id?: number; description?: string }> | string[],
    category: keyof typeof categoryConfig,
    emptyMessage: string
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
        {items.map((item, index) => {
          const text =
            typeof item === "string" ? item : item.description ?? "";
          const key = typeof item === "string" ? index : item.id ?? index;

          return (
            <div
              key={key}
              className={`p-3.5 rounded-md border-l-2 ${config.borderClass} ${
                config.bgClass
              } transition-colors`}
            >
              <p className="text-sm leading-relaxed">{text}</p>
            </div>
          );
        })}
      </div>
    );
  };

  const renderAccordionItem = (
    value: string,
    category: keyof typeof categoryConfig,
    count: number,
    children: ReactNode
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
              {count}
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
        {error && (
          <div className="mb-4 px-1 text-sm text-destructive">
            {error}
          </div>
        )}
        <Accordion type="multiple" className="w-full">
          {renderAccordionItem(
            "interventions",
            "interventions",
            interventions.length,
            renderCategoryItems(
              interventions,
              "interventions",
              "No interventions available"
            )
          )}

          {renderAccordionItem(
            "conditions",
            "conditions",
            conditions.length,
            renderCategoryItems(
              conditions,
              "conditions",
              "No conditions available"
            )
          )}

          {renderAccordionItem(
            "outcomes",
            "outcomes",
            outcomes.length,
            renderCategoryItems(
              outcomes,
              "outcomes",
              "No outcomes available"
            )
          )}

          {renderAccordionItem(
            "design",
            "design",
            design.length,
            renderCategoryItems(
              design,
              "design",
              "No design information available"
            )
          )}

          {renderAccordionItem(
            "persons",
            "persons",
            persons.length,
            renderCategoryItems(
              persons,
              "persons",
              "No persons information available"
            )
          )}
        </Accordion>
      </div>
    </div>
  );
}