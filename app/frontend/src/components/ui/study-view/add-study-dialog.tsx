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
import { Check, Plus, X } from "lucide-react";
import { toast } from "sonner";
import { COUNTRY_OPTIONS } from "./constants";
import { useStudyFieldValues } from "@/hooks/use-study-schema";
import {
  armDraftFromSuggestion,
  buildGraph,
  createComparisonGroup,
  hasValidComparisonGroups,
} from "@/lib/comparisonUtils";
import { useCallback, useEffect, useState } from "react";
import { useAbortableEffect } from "@/hooks/use-abortable-effect";
import { useElementHeight } from "@/hooks/use-element-height";
import { getSimilarTagsByReportId, getSuggestedStudyName } from "@/lib/api/reportApi";
import { getInterventions } from "@/lib/api/interventionsApi";
import type {
  ComparisonSuggestion,
  DurationUnit,
  NewStudySuggestion,
  StudyBaseDto,
} from "@/types/apiDTOs";
import type {
  ArmDraft,
  ComparisonGroup,
  ComparisonSideKey,
} from "@/types/comparisons";

const CATALOG_SEARCH_MIN_CHARS = 2;
const COMPARISON_CARD_VERTICAL_GAP = 12; // matches space-y-3 spacing to prevent clipping
const COMPARISON_PANEL_MAX_HEIGHT = "min(110vh, 900px)"; // hard cap so dialog never exceeds viewport
const buildEmptyComparisonGroups = () => [createComparisonGroup()];

const DURATION_UNITS: DurationUnit[] = ["hours", "days", "weeks", "months", "years"];

const UNIT_HOURS: Record<DurationUnit, number> = { hours: 1, days: 24, weeks: 168, months: 720, years: 8760 };

// The longest duration of the arms as the study will calculate it, e.g. "12 weeks"; empty if no arm has one.
const longestArmDuration = (groups: ComparisonGroup[]): string => {
  let longest: { value: number; unit: DurationUnit; hours: number } | null = null;
  for (const arm of groups.flatMap((group) => [group.a, group.b])) {
    const value = Number(arm.durationValue);
    if (!arm.durationUnit || !(value > 0)) continue;
    const hours = value * UNIT_HOURS[arm.durationUnit];
    if (!longest || hours > longest.hours) longest = { value, unit: arm.durationUnit, hours };
  }
  return longest ? `${longest.value} ${longest.unit}` : "";
};

const buildComparisonGroupsFromSuggestion = (
  groups?: ComparisonSuggestion[] | null
): ComparisonGroup[] => {
  if (!groups || groups.length === 0) {
    return buildEmptyComparisonGroups();
  }

  return groups.map((group) =>
    createComparisonGroup({
      a: armDraftFromSuggestion(group.a),
      b: armDraftFromSuggestion(group.b),
    })
  );
};

type SuggestionField = {
  groupId: string;
  side: ComparisonSideKey;
};

export interface AddStudyDialogProps {
  currentReportId?: number;
  suggestedValues?: NewStudySuggestion;
  onSaveStudy: (values: StudyBaseDto) => Promise<void>;
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
}: AddStudyDialogProps) {
  const [shortName, setShortName] = useState("");
  const statusOptions = useStudyFieldValues("status");
  const [statusOfStudy, setStatusOfStudy] = useState("");
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [numberOfParticipants, setNumberOfParticipants] = useState("");
  const [durationValue, setDurationValue] = useState("");
  const [durationUnit, setDurationUnit] = useState<DurationUnit | "">("");

  const [countryOpen, setCountryOpen] = useState(false);

  // Exposed as a `data-highlighted` attribute below rather than a class here,
  // so a downstream build can style a suggestion-prefilled dialog however it
  // wants without this component owning
  // any particular look.
  const highlight = Boolean(suggestedValues);

  // The arms (`${group id}-${side}`) whose details beyond the interventions are shown.
  const [openDetails, setOpenDetails] = useState<Set<string>>(new Set());
  const [comparisonGroups, setComparisonGroups] = useState<ComparisonGroup[]>(
    buildEmptyComparisonGroups()
  );

  const [activeSuggestionField, setActiveSuggestionField] = useState<
    SuggestionField | null
  >(null);
  const [suggestionQuery, setSuggestionQuery] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isFetchingSuggestions, setIsFetchingSuggestions] = useState(false);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [allInterventions, setAllInterventions] = useState<string[]>([]);

  const [addStudyDialogOpen, setAddStudyDialogOpen] = useState(false);
  const [creatingStudy, setCreatingStudy] = useState(false);
  const [firstComparisonElement, setFirstComparisonElement] = useState<HTMLDivElement | null>(null);

  const resetLocalFormState = useCallback(() => {
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
      setComparisonGroups(
        buildComparisonGroupsFromSuggestion(suggestedValues.comparisons)
      );
    } else {
      setShortName("");
      setStatusOfStudy("");
      setSelectedCountries([]);
      setNumberOfParticipants("");
      setDurationValue("");
      setDurationUnit("");
      setComparisonGroups(buildEmptyComparisonGroups());
    }
    setActiveSuggestionField(null);
    setSuggestionQuery("");
    setSuggestions([]);
    setIsFetchingSuggestions(false);
    setSuggestionError(null);
  }, [suggestedValues]);

  useEffect(() => {
    if (!addStudyDialogOpen) {
      resetLocalFormState();
    }
  }, [
    addStudyDialogOpen,
    resetLocalFormState,
  ]);

  useAbortableEffect(
    async (signal) => {
      if (!addStudyDialogOpen) return;

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
    [addStudyDialogOpen, currentReportId]
  );

  // Prefills the name unless the suggested values bring one.
  const hasSuggestedName = Boolean(suggestedValues?.short_name);
  useAbortableEffect(
    async (signal) => {
      if (!addStudyDialogOpen || !currentReportId || hasSuggestedName) return;

      try {
        const name = await getSuggestedStudyName(Number(currentReportId), { signal });
        // Not over what the user has typed in the meantime.
        if (!signal.aborted) setShortName((current) => current || name);
      } catch (error) {
        if (!signal.aborted) console.error("Failed to load the suggested study name:", error);
      }
    },
    [addStudyDialogOpen, currentReportId, hasSuggestedName]
  );

  useAbortableEffect(
    async (signal) => {
      if (!addStudyDialogOpen || allInterventions.length > 0) return;

      try {
        setAllInterventions(uniqueKeywords(await getInterventions({ signal })));
      } catch (error) {
        if (signal.aborted) return;
        console.error("Failed to load interventions:", error);
        setAllInterventions([]);
      }
    },
    [addStudyDialogOpen, allInterventions.length]
  );

  // With several comparisons the panel is capped at one card's height and scrolls.
  const firstCardHeight = useElementHeight(firstComparisonElement, comparisonGroups.length > 1);
  const comparisonPanelHeight =
    firstCardHeight === null ? null : firstCardHeight + COMPARISON_CARD_VERTICAL_GAP;

  const handleAddStudySubmit = async (
    event: React.FormEvent<HTMLFormElement>
  ) => {
    event.preventDefault();

    if (!currentReportId) {
      toast.error("Select a report before adding a study.");
      return;
    }

    // Both overall values are optional: left empty, the study calculates them from its arms.
    const participantsValue = numberOfParticipants.trim() === "" ? null : Number(numberOfParticipants);
    if (participantsValue !== null && Number.isNaN(participantsValue)) {
      toast.error("Enter a valid number of participants.");
      return;
    }
    const duration = durationValue.trim() && durationUnit ? `${durationValue.trim()} ${durationUnit}` : null;

    const graph = buildGraph(comparisonGroups);
    if (graph === null) {
      toast.error("Add at least one comparison with both sides populated.");
      return;
    }

    const normalizedCountries =
      selectedCountries.length > 0
        ? selectedCountries.map((country) => country.trim()).filter(Boolean)
        : ["Unclear"];

    const payload: StudyBaseDto = {
      shortName: shortName.trim(),
      status: statusOfStudy.trim(),
      countries: normalizedCountries,
      numberParticipants: participantsValue === null ? null : String(participantsValue),
      duration,
      graph,
      trialId: null, //TODO
    };

    setCreatingStudy(true);
    try {
      await onSaveStudy(payload);
      toast.success("New study created and linked to the report.");
      setAddStudyDialogOpen(false);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Failed to save study."
      );
    } finally {
      setCreatingStudy(false);
    }
  };

  const toggleCountrySelection = (country: string) => {
    setSelectedCountries((previous) =>
      previous.includes(country)
        ? previous.filter((entry) => entry !== country)
        : [...previous, country]
    );
  };

  const removeInterventionField = (
    groupId: string,
    side: ComparisonSideKey,
    index: number
  ) => {
    setComparisonGroups((previous) =>
      previous.map((group) => {
        if (group.id !== groupId) return group;
        const interventions = [...group[side].interventions];
        interventions.splice(index, 1);
        return {
          ...group,
          [side]: { ...group[side], interventions },
        };
      })
    );
  };

  const addComparisonGroup = () => {
    setComparisonGroups((previous) => [...previous, createComparisonGroup()]);
  };

  const removeComparisonGroup = (groupId: string) => {
    setComparisonGroups((previous) =>
      previous.length <= 1
        ? previous
        : previous.filter((group) => group.id !== groupId)
    );
  };

  const appendComparisonValue = (
    groupId: string,
    side: ComparisonSideKey,
    value: string
  ) => {
    const trimmed = value.trim();
    if (!trimmed) return;

    setComparisonGroups((previous) =>
      previous.map((group) =>
        group.id !== groupId
          ? group
          : {
              ...group,
              [side]: { ...group[side], interventions: [...group[side].interventions, trimmed] },
            }
      )
    );
  };

  const updateArm = (
    groupId: string,
    side: ComparisonSideKey,
    changes: Partial<ArmDraft>
  ) => {
    setComparisonGroups((previous) =>
      previous.map((group) =>
        group.id !== groupId ? group : { ...group, [side]: { ...group[side], ...changes } }
      )
    );
  };

  const isSuggestionFieldActive = (
    groupId: string,
    side: ComparisonSideKey
  ) =>
    activeSuggestionField?.groupId === groupId &&
    activeSuggestionField?.side === side;

  const renderSuggestionItem = (
    group: ComparisonGroup,
    side: ComparisonSideKey,
    item: string,
    source: "suggestion" | "catalog"
  ) => {
    const normalizedItem = item.toLowerCase();
    const matchIndex = group[side].interventions.findIndex(
      (entry) => entry.toLowerCase() === normalizedItem
    );
    const isSelected = matchIndex !== -1;

    return (
      <CommandItem
        key={`${group.id}-${side}-${source}-${item}`}
        value={item}
        aria-pressed={isSelected}
        onSelect={() => {
          if (isSelected) {
            removeInterventionField(group.id, side, matchIndex);
            return;
          }

          appendComparisonValue(group.id, side, item);
          if (isSuggestionFieldActive(group.id, side)) {
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

  const renderComparisonSideInputs = (
    group: ComparisonGroup,
    placeholderLabel: string,
    side: ComparisonSideKey
  ) => {
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
    const selectionSummary =
      group[side].interventions.length > 0
        ? `${group[side].interventions.length} ${placeholderLabel}${
            group[side].interventions.length > 1 ? "s" : ""
          } added`
        : `Select ${placeholderLabel.toLowerCase()}`;

    return (
      <div className="space-y-2">
        <Popover
          modal
          open={isSuggestionFieldActive(group.id, side)}
          onOpenChange={(open) => {
            if (open) {
              setActiveSuggestionField({ groupId: group.id, side });
              setSuggestionQuery("");
            } else if (isSuggestionFieldActive(group.id, side)) {
              setActiveSuggestionField(null);
              setSuggestionQuery("");
            }
          }}
        >
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant="outline"
              role="combobox"
              aria-expanded={isSuggestionFieldActive(group.id, side)}
              aria-label={`Select ${placeholderLabel}`}
              className="w-full justify-between"
            >
              <span className="truncate text-left text-muted-foreground">
                {selectionSummary}
              </span>
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
                          key={`${group.id}-${side}-custom-${trimmedQuery}`}
                          value={trimmedQuery}
                          onSelect={() => {
                            appendComparisonValue(group.id, side, trimmedQuery);
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
                          renderSuggestionItem(group, side, item, "suggestion")
                        )}
                      </CommandGroup>
                    )}
                    {catalogMatches.length > 0 && (
                      <CommandGroup heading="All interventions">
                        {catalogMatches.map((item) =>
                          renderSuggestionItem(group, side, item, "catalog")
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
                  placeholder={`Search ${placeholderLabel.toLowerCase()}...`}
                  className="h-8"
                />
              </div>
            </Command>
          </PopoverContent>
        </Popover>
        <div className="space-y-2 mt-1">
          {group[side].interventions.map((value, index) => (
            <div
              key={`${group.id}-${side}-${index}`}
              className="flex items-center justify-between gap-2 rounded-md border border-border/20 bg-muted px-3 py-1 text-sm text-muted-foreground"
            >
              <span className="flex-1 truncate">{value}</span>
              <Button
                variant="ghost"
                size="sm"
                type="button"
                onClick={() => removeInterventionField(group.id, side, index)}
                aria-label={`Remove ${placeholderLabel.toLowerCase()} ${index + 1}`}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
        {(() => {
          const arm = group[side];
          const detailKey = `${group.id}-${side}`;
          const open = openDetails.has(detailKey);
          const summary = [
            arm.participants && `${arm.participants} participants`,
            arm.dosage,
            arm.frequency,
            arm.route,
            arm.durationValue && arm.durationUnit && `${arm.durationValue} ${arm.durationUnit}`,
          ].filter(Boolean).join(" · ");
          return (
            <>
              <button
                type="button"
                className="flex w-full items-center gap-1 text-left text-xs text-muted-foreground hover:text-foreground"
                aria-expanded={open}
                onClick={() =>
                  setOpenDetails((previous) => {
                    const next = new Set(previous);
                    if (!next.delete(detailKey)) next.add(detailKey);
                    return next;
                  })
                }
              >
                <span>{open ? "−" : "+"}</span>
                <span className="shrink-0">{open ? "Hide arm details" : summary ? "Arm details" : "Add arm details"}</span>
                {!open && summary && <span className="min-w-0 flex-1 truncate">: {summary}</span>}
              </button>
              {open && (
                <div className="space-y-2">
          <Input
            aria-label={`Participants of the ${placeholderLabel.toLowerCase()} arm`}
            placeholder="Participants in this arm"
            type="number"
            min="0"
            value={group[side].participants}
            onChange={(event) => updateArm(group.id, side, { participants: event.target.value })}
          />
          <div className="grid grid-cols-[1fr_1fr] gap-2">
            <Input
              aria-label={`Dosage of the ${placeholderLabel.toLowerCase()} arm`}
              placeholder="Dosage, e.g. 10 mg"
              value={group[side].dosage}
              onChange={(event) => updateArm(group.id, side, { dosage: event.target.value })}
            />
            <Input
              aria-label={`Frequency of the ${placeholderLabel.toLowerCase()} arm`}
              placeholder="Frequency, e.g. daily"
              value={group[side].frequency}
              onChange={(event) => updateArm(group.id, side, { frequency: event.target.value })}
            />
          </div>
          <Input
            aria-label={`Route of the ${placeholderLabel.toLowerCase()} arm`}
            placeholder="Route, e.g. oral, injection"
            value={group[side].route}
            onChange={(event) => updateArm(group.id, side, { route: event.target.value })}
          />
          <div className="grid grid-cols-[1fr_1fr] gap-2">
            <Input
              aria-label={`Duration of the ${placeholderLabel.toLowerCase()} arm`}
              placeholder="Duration"
              type="number"
              min="0"
              value={group[side].durationValue}
              onChange={(event) => updateArm(group.id, side, { durationValue: event.target.value })}
            />
            <Select
              value={group[side].durationUnit || undefined}
              onValueChange={(value) => updateArm(group.id, side, { durationUnit: value as DurationUnit })}
            >
              <SelectTrigger className="w-full" aria-label={`Unit of the duration of the ${placeholderLabel.toLowerCase()} arm`}>
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
              )}
            </>
          );
        })()}
      </div>
    );
  };

  const normalizedCountry =
    selectedCountries.length > 0 ? selectedCountries.join(", ") : "Unclear";
  const longestArm = longestArmDuration(comparisonGroups);
  const hasMultipleComparisonGroups = comparisonGroups.length > 1;
  const comparisonValid = hasValidComparisonGroups(comparisonGroups);

  const isSubmitDisabled =
    creatingStudy ||
    shortName.trim().length === 0 ||
    statusOfStudy.trim().length === 0 ||
    !comparisonValid;

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
          <div className="grid gap-4 grid-cols-[7fr_3fr] w-full items-start">
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
          <div className="grid gap-4 grid-cols-[1fr_1fr] items-start">
            <div className="space-y-2">
              <Label htmlFor="study-participants">Number of participants</Label>
              <Input
                id="study-participants"
                type="number"
                min="0"
                placeholder="Empty: the sum of the arms"
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
                  placeholder={longestArm || "Longest arm"}
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
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-2">
              <Label className="text-sm font-semibold">Comparisons</Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={addComparisonGroup}
              >
                + Add comparison
              </Button>
            </div>
            <div className="rounded-lg border border-border/60 overflow-hidden">
              <div
                className={`space-y-3 p-3.5 ${hasMultipleComparisonGroups ? "overflow-y-auto" : ""}`}
                style={{
                  height:
                    hasMultipleComparisonGroups && comparisonPanelHeight
                      ? `${Math.round(comparisonPanelHeight)}px`
                      : undefined,
                  maxHeight: hasMultipleComparisonGroups
                    ? COMPARISON_PANEL_MAX_HEIGHT
                    : undefined,
                }}
              >
                {comparisonGroups.map((group, index) => (
                  <div
                    ref={index === 0 ? setFirstComparisonElement : undefined}
                    key={group.id}
                    className="space-y-3 rounded-lg border border-border/40 p-3.5"
                  >
                    <div
                      className="grid gap-3 items-start"
                      style={{
                        gridTemplateColumns:
                          "minmax(0,45%) minmax(0,10%) minmax(0,45%)",
                      }}
                    >
                      {renderComparisonSideInputs(group, "Intervention", "a")}
                      <div className="text-xs font-semibold text-muted-foreground flex items-center justify-center mt-2">
                        vs.
                      </div>
                      {renderComparisonSideInputs(group, "Control", "b")}
                    </div>
                    <div className="flex justify-end">
                      {comparisonGroups.length > 1 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          type="button"
                          onClick={() => removeComparisonGroup(group.id)}
                        >
                          Remove
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <DialogFooter>
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
