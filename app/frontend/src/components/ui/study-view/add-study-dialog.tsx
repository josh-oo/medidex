import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Check, Plus, X } from "lucide-react";
import { toast } from "sonner";
import { COUNTRY_OPTIONS } from "./constants";
import { useStudyFieldValues } from "@/hooks/use-study-schema";
import {
  areCompared,
  armFromSuggestion,
  armLetter,
  buildGraph,
  comparisonBetween,
  comparisonsFromSuggestion,
  createComparison,
  createStudyArm,
  detailsFromGraph,
  graphFromForm,
  hasValidComparisons,
  orderArms,
  suggestionFromGraph,
} from "@/lib/comparisonUtils";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useAbortableEffect } from "@/hooks/use-abortable-effect";
import { getSimilarTagsByReportId, getSuggestedStudyName } from "@/lib/api/reportApi";
import { getInterventions } from "@/lib/api/interventionsApi";
import type {
  DurationUnit,
  NewStudySuggestion,
  StudyBaseDto,
  StudyGraphDto,
} from "@/types/apiDTOs";
import type {
  ArmComparison,
  ArmRole,
  StudyArm,
  StudyDetails,
} from "@/types/comparisons";
import { ArmComparisonLanes, lanesWidth, useRowCenters } from "./arm-comparison-lanes";
import { StudyOutcomeFields, StudyPopulationFields } from "./study-details-fields";

const CATALOG_SEARCH_MIN_CHARS = 2;

// A new study starts with an intervention arm compared against a control arm.
const buildEmptyArms = (): { arms: StudyArm[]; comparisons: ArmComparison[] } => {
  const arms = [createStudyArm("intervention"), createStudyArm("control")];
  return { arms, comparisons: [createComparison(arms[0].id, arms[1].id)] };
};

const DURATION_UNITS: DurationUnit[] = ["hours", "days", "weeks", "months", "years"];

type ArmDetail = "participants" | "features" | "dosage" | "frequency" | "route" | "duration";

const ARM_DETAILS: { key: ArmDetail; label: string; placeholder: string }[] = [
  { key: "participants", label: "Participants", placeholder: "e.g. 40" },
  { key: "features", label: "Features", placeholder: "group, nurse-led, ..." },
  { key: "dosage", label: "Dosage", placeholder: "e.g. 5-10 mg" },
  { key: "frequency", label: "Frequency", placeholder: "e.g. once daily" },
  { key: "route", label: "Route", placeholder: "e.g. oral" },
  { key: "duration", label: "Duration", placeholder: "e.g. 12" },
];

const hasDetail = (arm: StudyArm, key: ArmDetail): boolean =>
  key === "duration" ? Boolean(arm.durationValue.trim() || arm.durationUnit) : Boolean(arm[key].trim());

const UNIT_HOURS: Record<DurationUnit, number> = { hours: 1, days: 24, weeks: 168, months: 720, years: 8760 };

// The longest duration of the arms as the study will calculate it, e.g. "12 weeks"; empty if no arm has one.
const longestArmDuration = (arms: StudyArm[]): string => {
  let longest: { value: number; unit: DurationUnit; hours: number } | null = null;
  for (const arm of arms) {
    const value = Number(arm.durationValue);
    if (!arm.durationUnit || !(value > 0)) continue;
    const hours = value * UNIT_HOURS[arm.durationUnit];
    if (!longest || hours > longest.hours) longest = { value, unit: arm.durationUnit, hours };
  }
  return longest ? `${longest.value} ${longest.unit}` : "";
};

// The participants of the arms added up, as the study will calculate them: only if every arm has a number (a part would
// understate the total); empty otherwise.
const armParticipantsSum = (arms: StudyArm[]): string => {
  const numbers = arms.map((arm) => Number(arm.participants));
  return arms.length > 0 && numbers.every((value) => Number.isInteger(value) && value > 0) ? String(numbers.reduce((sum, value) => sum + value, 0)) : "";
};

const buildArmsFromSuggestion = (
  suggestion: NewStudySuggestion
): { arms: StudyArm[]; comparisons: ArmComparison[] } => {
  if (suggestion.arms.length === 0) {
    return buildEmptyArms();
  }

  const arms = suggestion.arms.map(armFromSuggestion);
  return { arms, comparisons: comparisonsFromSuggestion(arms, suggestion.comparisons) };
};

export interface AddStudyDialogProps {
  currentReportId?: number;
  suggestedValues?: NewStudySuggestion;
  onSaveStudy: (values: StudyBaseDto) => Promise<void>;
  /** Shows the form in place (e.g. as a widget of the report workbench) instead of behind a button and dialog. */
  inline?: boolean;
  /**
   * Rendered beside the buttons of the form (e.g. a button that opens the whole graph): `current` gives the graph the
   * form makes as it is filled in, `apply` fills the form in from a graph (one edited from it).
   */
  graphAction?: (current: () => StudyGraphDto, apply: (graph: StudyGraphDto) => void) => ReactNode;
}

const uniqueKeywords = (data: unknown): string[] => {
  if (!Array.isArray(data)) return [];
  const keywords = data
    .map((entry) => (typeof entry === "string" ? entry : entry?.keyword))
    .filter((keyword): keyword is string => typeof keyword === "string" && keyword.length > 0);
  return Array.from(new Set(keywords));
};

export function AddStudyDialog({
  currentReportId,
  suggestedValues,
  onSaveStudy,
  inline = false,
  graphAction,
}: AddStudyDialogProps) {
  const [shortName, setShortName] = useState("");
  const statusOptions = useStudyFieldValues("status");
  const [statusOfStudy, setStatusOfStudy] = useState("");
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [numberOfParticipants, setNumberOfParticipants] = useState("");
  const [durationValue, setDurationValue] = useState("");
  const [durationUnit, setDurationUnit] = useState<DurationUnit | "">("");
  // Who the participants are, the design, trial ids and outcomes of the study.
  const [details, setDetails] = useState<StudyDetails>(() => detailsFromGraph());
  // The graph the form is written onto (the suggested one, or one applied with `graphAction`).
  const [baseGraph, setBaseGraph] = useState<StudyGraphDto | undefined>(undefined);

  const [countryOpen, setCountryOpen] = useState(false);

  // Exposed as a `data-highlighted` attribute below rather than a class here,
  // so a downstream build can style a suggestion-prefilled dialog however it
  // wants without this component owning
  // any particular look.
  const highlight = Boolean(suggestedValues);

  // Every arm once, and the comparisons between them (drawn as brackets beside the arms).
  const [arms, setArms] = useState<StudyArm[]>([]);
  const [comparisons, setComparisons] = useState<ArmComparison[]>([]);
  // The arm a new comparison is being drawn from (its port was clicked), until the port of another arm is.
  const [linkingFrom, setLinkingFrom] = useState<string | null>(null);
  const [armsElement, setArmsElement] = useState<HTMLDivElement | null>(null);
  const rowCenters = useRowCenters(armsElement);
  // An arm shows only the details it has, and those added with "+ Attribute" until they are left empty.
  const [openedDetails, setOpenedDetails] = useState<Record<string, ArmDetail[]>>({});

  // The arm whose intervention picker is open.
  const [activeSuggestionField, setActiveSuggestionField] = useState<string | null>(null);
  const [suggestionQuery, setSuggestionQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isFetchingSuggestions, setIsFetchingSuggestions] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [allInterventions, setAllInterventions] = useState<string[]>([]);

  const [addStudyDialogOpen, setAddStudyDialogOpen] = useState(false);
  // An inline form is always shown, so it loads its suggestions right away.
  const isFormShown = inline || addStudyDialogOpen;
  const [creatingStudy, setCreatingStudy] = useState(false);

  const resetLocalFormState = useCallback(() => {
    const initial = suggestedValues ? buildArmsFromSuggestion(suggestedValues) : buildEmptyArms();
    setArms(orderArms(initial.arms));
    setComparisons(initial.comparisons);
    setLinkingFrom(null);
    setOpenedDetails({});
    setDetails(detailsFromGraph(suggestedValues?.graph));
    setBaseGraph(suggestedValues?.graph);
    if (suggestedValues) {
      setShortName(suggestedValues.short_name ?? "");
      setStatusOfStudy(suggestedValues.status_of_study ?? "");
      setSelectedCountries(suggestedValues.countries);
      setNumberOfParticipants(
        suggestedValues.number_of_participants
          ? String(suggestedValues.number_of_participants)
          : ""
      );
      setDurationValue(suggestedValues.duration ? String(suggestedValues.duration.value) : "");
      setDurationUnit(suggestedValues.duration?.unit ?? "");
    } else {
      setShortName("");
      setStatusOfStudy("");
      setSelectedCountries([]);
      setNumberOfParticipants("");
      setDurationValue("");
      setDurationUnit("");
    }
    setActiveSuggestionField(null);
    setSuggestionQuery("");
    setSuggestions([]);
    setIsFetchingSuggestions(false);
    setSuggestionError(null);
  }, [suggestedValues]);

  // A dialog starts over whenever it closes; an inline form whenever the report or its suggestion changes.
  useEffect(() => {
    if (inline || !addStudyDialogOpen) {
      resetLocalFormState();
    }
  }, [
    inline,
    addStudyDialogOpen,
    resetLocalFormState,
    currentReportId,
  ]);

  useAbortableEffect(
    async (signal) => {
      if (!isFormShown) return;

      if (!currentReportId) {
        setSuggestionError("Select a report to load intervention suggestions.");
        setSuggestions([]);
        setIsFetchingSuggestions(false);
        return;
      }

      setIsFetchingSuggestions(true);
      setSuggestionError(null);

      try {
        const data = await getSimilarTagsByReportId(Number(currentReportId), {}, { signal });
        setSuggestions(uniqueKeywords(data));
      } catch (error) {
        if (signal.aborted) return;
        setSuggestionError(
          error instanceof Error ? error.message : "Failed to load intervention tags."
        );
        setSuggestions([]);
      } finally {
        if (!signal.aborted) setIsFetchingSuggestions(false);
      }
    },
    [isFormShown, currentReportId]
  );

  // Prefills the name unless the suggested values bring one.
  const hasSuggestedName = Boolean(suggestedValues?.short_name);
  useAbortableEffect(
    async (signal) => {
      if (!isFormShown || !currentReportId || hasSuggestedName) return;

      try {
        const name = await getSuggestedStudyName(Number(currentReportId), { signal });
        // Not over what the user has typed in the meantime.
        if (!signal.aborted) setShortName((current) => current || name);
      } catch (error) {
        if (!signal.aborted) console.error("Failed to load the suggested study name:", error);
      }
    },
    [isFormShown, currentReportId, hasSuggestedName]
  );

  useAbortableEffect(
    async (signal) => {
      if (!isFormShown || allInterventions.length > 0) return;

      try {
        setAllInterventions(uniqueKeywords(await getInterventions({ signal })));
      } catch (error) {
        if (signal.aborted) return;
        console.error("Failed to load interventions:", error);
        setAllInterventions([]);
      }
    },
    [isFormShown, allInterventions.length]
  );

  // Escape cancels a comparison being drawn, before the dialog would close on it.
  useEffect(() => {
    if (linkingFrom === null) return;
    const cancel = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      setLinkingFrom(null);
    };
    window.addEventListener("keydown", cancel, true);
    return () => window.removeEventListener("keydown", cancel, true);
  }, [linkingFrom]);

  const handleAddStudySubmit = async (
    event: React.FormEvent<HTMLFormElement>
  ) => {
    event.preventDefault();

    if (!currentReportId) {
      toast.error("Select a report before adding a study.");
      return;
    }

    // Both overall values are optional: left empty, the study calculates them from its arms. Like everything of the form
    // they are written into the graph, the only source of what the study says (onto the graph it was prefilled from).
    const participantsValue = numberOfParticipants.trim() === "" ? null : Number(numberOfParticipants);
    if (participantsValue !== null && (Number.isNaN(participantsValue) || !Number.isInteger(participantsValue) || participantsValue < 0)) {
      toast.error("Enter a valid number of participants.");
      return;
    }
    const duration = durationValue.trim() && durationUnit ? `${durationValue.trim()} ${durationUnit}` : undefined;

    const graph = buildGraph(arms, comparisons, selectedCountries, baseGraph, {
      duration,
      participants: participantsValue === null ? undefined : String(participantsValue),
      details,
    });
    if (graph === null) {
      toast.error("Compare at least two arms that have interventions.");
      return;
    }

    const payload: StudyBaseDto = {
      shortName: shortName.trim(),
      status: statusOfStudy.trim(),
      // Views of the graph (above), which holds them.
      numberParticipants: null,
      duration: null,
      graph,
      trialId: null, //TODO
    };

    setCreatingStudy(true);
    try {
      await onSaveStudy(payload);
      toast.success("New study created and linked to the report.");
      setAddStudyDialogOpen(false);
      if (inline) resetLocalFormState();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to save study."
      );
    } finally {
      setCreatingStudy(false);
    }
  };

  // The graph the form makes as it is (whatever its comparisons), and the form filled in from a graph; the name and the
  // status are not part of a graph and stay.
  const currentGraph = () => {
    const duration = durationValue.trim() && durationUnit ? `${durationValue.trim()} ${durationUnit}` : undefined;
    return graphFromForm(arms, comparisons, selectedCountries, baseGraph, {
      duration,
      participants: numberOfParticipants.trim() || undefined,
      details,
    });
  };
  const applyGraph = (graph: StudyGraphDto) => {
    const suggestion = suggestionFromGraph(graph, shortName);
    const initial = buildArmsFromSuggestion(suggestion);
    setArms(orderArms(initial.arms));
    setComparisons(initial.comparisons);
    setLinkingFrom(null);
    setOpenedDetails({});
    setSelectedCountries(suggestion.countries);
    setNumberOfParticipants(suggestion.number_of_participants ? String(suggestion.number_of_participants) : "");
    // A duration of the study is that of its arms in the graph.
    setDurationValue("");
    setDurationUnit("");
    setDetails(detailsFromGraph(graph));
    setBaseGraph(graph);
  };

  const toggleCountrySelection = (country: string) => {
    setSelectedCountries((previous) =>
      previous.includes(country)
        ? previous.filter((entry) => entry !== country)
        : [...previous, country]
    );
  };

  // An arm keeps its place when its type changes; only the arms of a suggestion are ordered by type.
  const updateArm = (armId: string, changes: Partial<StudyArm>) => {
    setArms((previous) => previous.map((arm) => (arm.id !== armId ? arm : { ...arm, ...changes })));
  };

  const openDetail = (armId: string, key: ArmDetail) => {
    setOpenedDetails((previous) => ({ ...previous, [armId]: [...(previous[armId] ?? []), key] }));
  };

  const closeDetail = (armId: string, key: ArmDetail) => {
    setOpenedDetails((previous) => ({ ...previous, [armId]: (previous[armId] ?? []).filter((entry) => entry !== key) }));
  };

  const removeInterventionField = (armId: string, index: number) => {
    setArms((previous) =>
      previous.map((arm) => (arm.id !== armId ? arm : { ...arm, interventions: arm.interventions.filter((_, position) => position !== index) }))
    );
  };

  const appendComparisonValue = (armId: string, value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setArms((previous) => previous.map((arm) => (arm.id !== armId ? arm : { ...arm, interventions: [...arm.interventions, trimmed] })));
  };

  const addArm = () => {
    setArms((previous) => orderArms([...previous, createStudyArm("intervention")]));
  };

  // An arm goes with its comparisons; a study keeps at least two arms.
  const removeArm = (armId: string) => {
    setArms((previous) => (previous.length <= 2 ? previous : previous.filter((arm) => arm.id !== armId)));
    setComparisons((previous) => previous.filter((comparison) => comparison.source !== armId && comparison.target !== armId));
    setLinkingFrom((current) => (current === armId ? null : current));
  };

  // The port of an arm starts a comparison from it, the port of another arm ends it there (once per pair of arms), its own
  // port again cancels it.
  const handlePort = (armId: string) => {
    if (linkingFrom === null) {
      setLinkingFrom(armId);
      return;
    }
    const [from, to] = [arms.find((arm) => arm.id === linkingFrom), arms.find((arm) => arm.id === armId)];
    if (from && to && from.id !== to.id && !areCompared(comparisons, from.id, to.id)) {
      setComparisons((previous) => [...previous, comparisonBetween(from, to)]);
    }
    setLinkingFrom(null);
  };

  const removeComparison = (comparisonId: string) => {
    setComparisons((previous) => previous.filter((comparison) => comparison.id !== comparisonId));
  };

  const isSuggestionFieldActive = (armId: string) => activeSuggestionField === armId;

  const renderSuggestionItem = (
    arm: StudyArm,
    item: string,
    source: "suggestion" | "catalog"
  ) => {
    const normalizedItem = item.toLowerCase();
    const matchIndex = arm.interventions.findIndex(
      (entry) => entry.toLowerCase() === normalizedItem
    );
    const isSelected = matchIndex !== -1;

    return (
      <CommandItem
        key={`${arm.id}-${source}-${item}`}
        value={item}
        aria-pressed={isSelected}
        onSelect={() => {
          if (isSelected) {
            removeInterventionField(arm.id, matchIndex);
            return;
          }

          appendComparisonValue(arm.id, item);
          if (isSuggestionFieldActive(arm.id)) {
            setSuggestionQuery("");
          }
        }}
        className="flex items-center gap-2"
      >
        <span className="flex-1 truncate text-left">{item}</span>
        <Check
          className={`h-4 w-4 text-primary transition-opacity ${
            isSelected ? "opacity-100" : "opacity-0"
          }`}
        />
      </CommandItem>
    );
  };

  const renderArmRow = (arm: StudyArm, index: number) => {
    const letter = armLetter(index);
    const trimmedQuery = suggestionQuery.trim();
    const normalizedQuery = trimmedQuery.toLowerCase();
    const filteredSuggestions = normalizedQuery
      ? suggestions.filter((item) =>
          item.toLowerCase().includes(normalizedQuery)
        )
      : suggestions;
    const suggestedSet = new Set(suggestions.map((item) => item.toLowerCase()));
    const catalogMatches =
      normalizedQuery.length >= CATALOG_SEARCH_MIN_CHARS
        ? allInterventions.filter(
            (item) =>
              item.toLowerCase().includes(normalizedQuery) &&
              !suggestedSet.has(item.toLowerCase())
          )
        : [];
    const canAddCustomValue =
      Boolean(trimmedQuery) &&
      !suggestedSet.has(normalizedQuery) &&
      !allInterventions.some((item) => item.toLowerCase() === normalizedQuery);
    const opened = openedDetails[arm.id] ?? [];
    const shownDetails = ARM_DETAILS.filter(({ key }) => hasDetail(arm, key) || opened.includes(key));
    const hiddenDetails = ARM_DETAILS.filter((detail) => !shownDetails.includes(detail));
    // A detail just added is focused; one left empty is hidden again.
    const blurDetail = (key: ArmDetail) => (event: React.FocusEvent<HTMLElement>) => {
      if (event.currentTarget.parentElement?.contains(event.relatedTarget as Node | null)) return;
      if (!hasDetail(arm, key)) closeDetail(arm.id, key);
    };
    const renderDetail = ({ key, label, placeholder }: (typeof ARM_DETAILS)[number]) => (
      <div key={key} className={`space-y-0.5 ${key === "duration" ? "w-[176px]" : key === "participants" ? "w-[96px]" : "w-[148px]"}`}>
        <span className="block px-1 text-[10px] font-medium text-muted-foreground">{label}</span>
        {key === "duration" ? (
          <div className="flex gap-1">
            <Input
              aria-label={`Duration of arm ${letter}`}
              placeholder={placeholder}
              type="number"
              min="0"
              autoFocus={opened.includes(key) && !hasDetail(arm, key)}
              className="h-8 w-[72px] text-xs"
              value={arm.durationValue}
              onChange={(event) => updateArm(arm.id, { durationValue: event.target.value })}
              onBlur={blurDetail(key)}
            />
            <Select
              value={arm.durationUnit || undefined}
              onValueChange={(value) => updateArm(arm.id, { durationUnit: value as DurationUnit })}
            >
              <SelectTrigger size="sm" className="h-8 flex-1 text-xs" aria-label={`Unit of the duration of arm ${letter}`}>
                <SelectValue placeholder="Unit" />
              </SelectTrigger>
              <SelectContent>
                {DURATION_UNITS.map((unit) => (
                  <SelectItem key={unit} value={unit}>
                    {unit}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : (
          <Input
            aria-label={`${label} of arm ${letter}`}
            placeholder={placeholder}
            type={key === "participants" ? "number" : undefined}
            min={key === "participants" ? "0" : undefined}
            autoFocus={opened.includes(key) && !hasDetail(arm, key)}
            className="h-8 text-xs"
            value={arm[key]}
            onChange={(event) => updateArm(arm.id, { [key]: event.target.value })}
            onBlur={blurDetail(key)}
          />
        )}
      </div>
    );

    return (
      <div key={arm.id} data-arm-row className="space-y-2 rounded-lg border border-border/60 bg-background p-2.5">
        <div className="flex items-start gap-2">
          <span
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-sm font-bold ${
              arm.role === "control" ? "bg-muted text-muted-foreground" : "bg-foreground/15 text-foreground"
            }`}
          >
            {letter}
          </span>
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 pt-1">
            {arm.interventions.map((value, position) => (
              <span
                key={`${arm.id}-${position}`}
                className="inline-flex max-w-full items-center gap-1 rounded-full border border-border/60 bg-muted py-0.5 pl-2.5 pr-1 text-xs"
              >
                <span className="truncate">{value}</span>
                <button
                  type="button"
                  className="rounded-full p-0.5 text-muted-foreground hover:text-foreground"
                  onClick={() => removeInterventionField(arm.id, position)}
                  aria-label={`Remove ${value} from arm ${letter}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
        <Popover
          modal
          open={isSuggestionFieldActive(arm.id)}
          onOpenChange={(open) => {
            if (open) {
              setActiveSuggestionField(arm.id);
              setSuggestionQuery("");
            } else if (isSuggestionFieldActive(arm.id)) {
              setActiveSuggestionField(null);
              setSuggestionQuery("");
            }
          }}
        >
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="outline"
              size="sm"
              role="combobox"
              aria-expanded={isSuggestionFieldActive(arm.id)}
              aria-label={`Add an intervention to arm ${letter}`}
              className="h-6 rounded-full border-dashed px-2.5 text-xs text-muted-foreground"
            >
              + Intervention
            </Button>
          </PopoverTrigger>
          <PopoverContent
            align="start"
            className="w-[min(420px,calc(100vw-3rem))] max-w-screen-sm overflow-hidden p-0"
            sideOffset={6}
          >
            <Command className="w-full min-w-[320px] text-xs">
              <CommandList className="max-h-[280px] overflow-y-auto overscroll-contain">
                {isFetchingSuggestions ? (
                  <CommandEmpty className="py-4 text-muted-foreground">
                    Loading suggestions...
                  </CommandEmpty>
                ) : (
                  <>
                    {suggestionError && (
                      <div className="px-3 py-2 text-destructive">
                        {suggestionError}
                      </div>
                    )}
                    {canAddCustomValue && (
                      <CommandGroup heading="Custom value">
                        <CommandItem
                          key={`${arm.id}-custom-${trimmedQuery}`}
                          value={trimmedQuery}
                          onSelect={() => {
                            appendComparisonValue(arm.id, trimmedQuery);
                            setSuggestionQuery("");
                          }}
                        >
                          Add "{trimmedQuery}"
                        </CommandItem>
                      </CommandGroup>
                    )}
                    {filteredSuggestions.length > 0 && (
                      <CommandGroup heading="Suggestions">
                        {filteredSuggestions.map((item) =>
                          renderSuggestionItem(arm, item, "suggestion")
                        )}
                      </CommandGroup>
                    )}
                    {catalogMatches.length > 0 && (
                      <CommandGroup heading="All interventions">
                        {catalogMatches.map((item) =>
                          renderSuggestionItem(arm, item, "catalog")
                        )}
                      </CommandGroup>
                    )}
                    {filteredSuggestions.length === 0 &&
                      catalogMatches.length === 0 && (
                        <CommandEmpty className="py-4 text-muted-foreground">
                          {normalizedQuery.length > 0 &&
                          normalizedQuery.length < CATALOG_SEARCH_MIN_CHARS
                            ? `Type at least ${CATALOG_SEARCH_MIN_CHARS} characters to search all interventions.`
                            : suggestionQuery
                              ? `No interventions matching "${suggestionQuery}".`
                              : "No intervention suggestions available."}
                        </CommandEmpty>
                      )}
                  </>
                )}
              </CommandList>
              <div className="border-t border-border/40 bg-muted/40 p-2">
                <CommandInput
                  value={suggestionQuery}
                  onValueChange={(value) => setSuggestionQuery(value)}
                  placeholder="Search interventions..."
                  className="h-8"
                />
              </div>
            </Command>
          </PopoverContent>
        </Popover>
          </div>
          <Select value={arm.role} onValueChange={(value) => updateArm(arm.id, { role: value as ArmRole })}>
            <SelectTrigger size="sm" className="h-8 w-[124px] shrink-0 text-xs" aria-label={`Type of arm ${letter}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="intervention">Intervention</SelectItem>
              <SelectItem value="control">Control</SelectItem>
            </SelectContent>
          </Select>
          {arms.length > 2 && (
            <Button
              variant="ghost"
              size="sm"
              type="button"
              className="h-8 w-8 shrink-0 p-0"
              onClick={() => removeArm(arm.id)}
              aria-label={`Remove arm ${letter}`}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-1.5 pl-10">
          {shownDetails.map(renderDetail)}
          {hiddenDetails.length > 0 && (
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  aria-label={`Add an attribute to arm ${letter}`}
                  className="h-6 rounded-full border-dashed px-2.5 text-xs text-muted-foreground"
                >
                  <Plus className="h-3 w-3" />
                  Attribute
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" onCloseAutoFocus={(event) => event.preventDefault()}>
                {hiddenDetails.map(({ key, label }) => (
                  <DropdownMenuItem key={key} className="text-xs" onSelect={() => openDetail(arm.id, key)}>
                    {label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    );
  };

  const normalizedCountry =
    selectedCountries.length > 0 ? selectedCountries.join(", ") : "Unclear";
  const longestArm = longestArmDuration(arms);
  const armsSum = armParticipantsSum(arms);
  const comparisonValid = hasValidComparisons(arms, comparisons);

  const isSubmitDisabled =
    creatingStudy ||
    shortName.trim().length === 0 ||
    statusOfStudy.trim().length === 0 ||
    !comparisonValid;

  const formFields = (
    <>
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-[7fr_3fr] w-full items-start">
            <div className="space-y-2">
              <Label htmlFor="study-short-name">Short name</Label>
              <Input
                id="study-short-name"
                placeholder="e.g. Steiner 1995"
                value={shortName}
                onChange={(event) => setShortName(event.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label>Status of study</Label>
              <Select
                value={statusOfStudy}
                onValueChange={(value) => setStatusOfStudy(value)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Choose status" />
                </SelectTrigger>
                <SelectContent>
                  {statusOptions.map((status) => (
                    <SelectItem key={status} value={status}>
                      {status}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="study-countries">Countries</Label>
            <Popover open={countryOpen} onOpenChange={setCountryOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={countryOpen}
                  className="w-full justify-between"
                >
                  {normalizedCountry}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[480px] max-w-screen-sm p-0 overflow-x-auto">
                <Command className="min-w-[420px]">
                  <CommandInput placeholder="Search country..." />
                  <CommandList className="max-h-[300px] overflow-y-auto overflow-x-auto">
                    <CommandEmpty>No country found.</CommandEmpty>
                    <CommandGroup>
                      {COUNTRY_OPTIONS.map((country) => {
                        const isSelected = selectedCountries.includes(country);
                        return (
                          <CommandItem
                            key={country}
                            value={country}
                            onSelect={() => toggleCountrySelection(country)}
                            aria-pressed={isSelected}
                          >
                            <span className="flex-1">{country}</span>
                            {isSelected && (
                              <Check className="h-4 w-4 text-primary" />
                            )}
                          </CommandItem>
                        );
                      })}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
          </div>
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-[1fr_1fr] items-start">
            <div className="space-y-2">
              <Label htmlFor="study-participants">Number of participants</Label>
              <Input
                id="study-participants"
                type="number"
                min="0"
                placeholder={armsSum ? `${armsSum} (sum of the arms)` : "Empty: the sum of the arms"}
                value={numberOfParticipants}
                onChange={(event) => setNumberOfParticipants(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="study-duration">Duration</Label>
              <div className="grid grid-cols-[1fr_1fr] gap-2">
                <Input
                  id="study-duration"
                  type="number"
                  min="0"
                  placeholder={longestArm || "Duration"}
                  value={durationValue}
                  onChange={(event) => setDurationValue(event.target.value)}
                />
                <Select value={durationUnit || undefined} onValueChange={(value) => setDurationUnit(value as DurationUnit)}>
                  <SelectTrigger className="w-full" aria-label="Unit of the duration of the study">
                    <SelectValue placeholder="Unit" />
                  </SelectTrigger>
                  <SelectContent>
                    {DURATION_UNITS.map((unit) => (
                      <SelectItem key={unit} value={unit}>
                        {unit}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          </div>
          <StudyPopulationFields details={details} onChange={setDetails} shown={isFormShown} />
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <Label className="text-sm font-semibold">Arms and comparisons</Label>
              <Button type="button" variant="ghost" size="sm" onClick={addArm}>
                + Add arm
              </Button>
            </div>
            <div ref={setArmsElement} className="relative" style={{ paddingLeft: lanesWidth(arms, comparisons) }}>
              <ArmComparisonLanes
                arms={arms}
                comparisons={comparisons}
                rowCenters={rowCenters}
                linkingFrom={linkingFrom}
                onPort={handlePort}
                onRemove={removeComparison}
              />
              <div className="space-y-2">{arms.map(renderArmRow)}</div>
            </div>
          </div>
          <StudyOutcomeFields details={details} onChange={setDetails} shown={isFormShown} />
    </>
  );

  if (inline) {
    return (
      <form className="space-y-4 w-full" onSubmit={handleAddStudySubmit}>
        {formFields}
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
            {graphAction && <div className="sm:mr-auto">{graphAction(currentGraph, applyGraph)}</div>}
            <Button
              type="button"
              variant="ghost"
              onClick={resetLocalFormState}
              disabled={creatingStudy}
            >
              Reset
            </Button>
            <Button
              type="submit"
              disabled={isSubmitDisabled}
              data-highlighted={highlight || undefined}
            >
              {creatingStudy ? "Saving..." : "Save Study"}
            </Button>
          </div>
      </form>
    );
  }

  return (
    <Dialog open={addStudyDialogOpen} onOpenChange={setAddStudyDialogOpen}>
      <Button
        type="button"
        variant="outline"
        className="w-full h-10 border-dashed text-muted-foreground hover:text-foreground"
        data-highlighted={highlight || undefined}
        aria-haspopup="dialog"
        aria-expanded={addStudyDialogOpen}
        onClick={() => setAddStudyDialogOpen(true)}
      >
        <Plus className="h-4 w-4" />
        Add as new study
      </Button>
      <DialogContent
        className="max-w-[900px] sm:max-w-[720px] w-[min(92vw,900px)] max-h-[90vh] overflow-y-auto"
        onOpenAutoFocus={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>Add New Study</DialogTitle>
          <DialogDescription>
            Link this report to a new study.
          </DialogDescription>
        </DialogHeader>
        <form className="space-y-4 w-full" onSubmit={handleAddStudySubmit}>
          {formFields}
          <DialogFooter>
            {graphAction && <div className="sm:mr-auto">{graphAction(currentGraph, applyGraph)}</div>}
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setAddStudyDialogOpen(false);
              }}
              disabled={creatingStudy}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isSubmitDisabled}
            >
              {creatingStudy ? "Saving..." : "Save Study"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
