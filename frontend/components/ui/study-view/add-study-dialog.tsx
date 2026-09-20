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
import { Check, X } from "lucide-react";
import { toast } from "sonner";
import { COUNTRY_OPTIONS } from "./constants";
import {
  createComparisonGroup,
  hasValidComparisonGroups,
} from "@/lib/comparisonUtils";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type {
  DurationUnit,
  InterventionDto,
  NewStudySuggestion,
  StudyCreateDto,
  ComparisonGroup as SuggestedComparisonGroup,
} from "@/types/apiDTOs";
import type {
  ComparisonGroup,
  ComparisonSideKey,
} from "@/types/comparisons";

const CATALOG_SEARCH_MIN_CHARS = 2;
const COMPARISON_CARD_VERTICAL_GAP = 12; // matches space-y-3 spacing to prevent clipping
const COMPARISON_PANEL_MAX_HEIGHT = 1.1; // portion of viewport for comparisons scroll region (roughly 2x previous)
const COMPARISON_PANEL_MAX_PIXEL = 900; // hard cap so dialog never exceeds viewport
const buildEmptyComparisonGroups = () => [createComparisonGroup()];

const buildComparisonGroupsFromSuggestion = (
  groups?: SuggestedComparisonGroup | SuggestedComparisonGroup[] | null
): ComparisonGroup[] => {
  if (!groups) {
    return buildEmptyComparisonGroups();
  }

  const normalized = Array.isArray(groups) ? groups : [groups];
  if (normalized.length === 0) {
    return buildEmptyComparisonGroups();
  }

  return normalized.map((group) =>
    createComparisonGroup({
      a: [...(group?.intervention ?? [])],
      b: [...(group?.control ?? [])],
    })
  );
};

type SuggestionField = {
  groupId: string;
  side: ComparisonSideKey;
};

type StudyDurationUnit = DurationUnit | "Uncertain";

interface AddStudyDialogProps {
  currentReportId?: number;
  suggestedValues?: NewStudySuggestion;
  onSaveStudy: (values: StudyCreateDto) => Promise<void>;
}

const buildComparisonPayload = (groups: ComparisonGroup[]) =>
  groups
    .map((group) => ({
      intervention: group.a.map((value) => value.trim()).filter(Boolean),
      control: group.b.map((value) => value.trim()).filter(Boolean),
    }))
    .filter((group) => group.intervention.length > 0 && group.control.length > 0);
export function AddStudyDialog({
  currentReportId,
  suggestedValues,
  onSaveStudy,
}: AddStudyDialogProps) {
  const [shortName, setShortName] = useState("");
  const [statusOfStudy, setStatusOfStudy] = useState("");
  const [durationValue, setDurationValue] = useState("");
  const [durationUnit, setDurationUnit] = useState<StudyDurationUnit | undefined>(
    undefined
  );
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [numberOfParticipants, setNumberOfParticipants] = useState("");

  const [countryOpen, setCountryOpen] = useState(false);

  const highlight = Boolean(suggestedValues);

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
  const firstComparisonRef = useRef<HTMLDivElement | null>(null);
  const [comparisonPanelHeight, setComparisonPanelHeight] = useState<number | null>(null);

  const resetLocalFormState = useCallback(() => {
    if (suggestedValues) {
      setShortName(suggestedValues.short_name ?? "");
      setStatusOfStudy(suggestedValues.status_of_study ?? "");
      setSelectedCountries(suggestedValues.countries);
      setDurationValue(
        suggestedValues.duration_value
          ? String(suggestedValues.duration_value)
          : ""
      );
      setDurationUnit(suggestedValues.duration_unit);
      setNumberOfParticipants(
        suggestedValues.number_of_participants
          ? String(suggestedValues.number_of_participants)
          : ""
      );
      setComparisonGroups(
        buildComparisonGroupsFromSuggestion(suggestedValues.comparison)
      );
    } else {
      setShortName("");
      setStatusOfStudy("");
      setSelectedCountries([]);
      setDurationValue("");
      setDurationUnit(undefined);
      setNumberOfParticipants("");
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
      return;
    }
  }, [
    addStudyDialogOpen,
    resetLocalFormState,
  ]);

  useEffect(() => {
    if (!addStudyDialogOpen) return;

    if (!currentReportId) {
      setSuggestionError("Select a report to load intervention suggestions.");
      setSuggestions([]);
      setIsFetchingSuggestions(false);
      return;
    }

    const controller = new AbortController();

    const loadInterventionTags = async () => {
      setIsFetchingSuggestions(true);
      setSuggestionError(null);

      try {
        const response = await fetch(
          `/api/meerkat/reports/${currentReportId}/similar-studies/tags`,
          { signal: controller.signal,
            cache: "no-store",
           },
        );

        if (!response.ok) {
          throw new Error("Failed to load intervention tags.");
        }

        const data = await response.json();
        const parsedSuggestions = Array.isArray(data)
          ? data
              .map((entry: { name?: string } | string | null) => {
                if (typeof entry === "string") return entry;
                if (entry && typeof entry === "object" && typeof entry.name === "string") {
                  return entry.name;
                }
                return null;
              })
              .filter((entry): entry is string => Boolean(entry))
          : [];

        setSuggestions(Array.from(new Set(parsedSuggestions)));
      } catch (error) {
        if (controller.signal.aborted) return;
        setSuggestionError(
          error instanceof Error
            ? error.message
            : "Failed to load intervention tags."
        );
        setSuggestions([]);
      } finally {
        if (!controller.signal.aborted) {
          setIsFetchingSuggestions(false);
        }
      }
    };

    loadInterventionTags();

    return () => {
      controller.abort();
    };
  }, [addStudyDialogOpen, currentReportId]);

  useEffect(() => {
    if (!addStudyDialogOpen || allInterventions.length > 0) return;

    const controller = new AbortController();

    const loadAllInterventions = async () => {
      try {
        const response = await fetch("/api/meerkat/interventions", {
          signal: controller.signal,
          cache: "no-store",
        });

        if (!response.ok) {
          throw new Error("Failed to load interventions.");
        }

        const data: InterventionDto[] = await response.json();
        const descriptions = Array.isArray(data)
          ? data
              .map((entry) => entry?.Description)
              .filter((entry): entry is string => Boolean(entry))
          : [];

        setAllInterventions(Array.from(new Set(descriptions)));
      } catch (error) {
        if (controller.signal.aborted) return;
        console.error("Failed to load interventions:", error);
        setAllInterventions([]);
      }
    };

    loadAllInterventions();

    return () => {
      controller.abort();
    };
  }, [addStudyDialogOpen, allInterventions.length]);

  useLayoutEffect(() => {
    if (!addStudyDialogOpen) {
      setComparisonPanelHeight(null);
      return;
    }

    if (comparisonGroups.length <= 1) {
      setComparisonPanelHeight(null);
      return;
    }

    const measureHeight = () => {
      if (!firstComparisonRef.current) {
        setComparisonPanelHeight(null);
        return;
      }

      const measuredHeight = firstComparisonRef.current.getBoundingClientRect().height;
      if (measuredHeight > 0) {
        const baseHeight = measuredHeight + COMPARISON_CARD_VERTICAL_GAP;
        setComparisonPanelHeight(baseHeight);
      }
    };

    measureHeight();
    window.addEventListener("resize", measureHeight);

    return () => {
      window.removeEventListener("resize", measureHeight);
    };
  }, [comparisonGroups, addStudyDialogOpen]);

  const handleAddStudySubmit = async (
    event: React.FormEvent<HTMLFormElement>
  ) => {
    event.preventDefault();

    if (!currentReportId) {
      toast.error("Select a report before adding a study.");
      return;
    }

    const participantsValue = Number(numberOfParticipants);
    if (Number.isNaN(participantsValue)) {
      toast.error("Enter a valid number of participants.");
      return;
    }

    const normalizedDuration =
      durationUnit === "Uncertain"
        ? "Uncertain"
        : durationUnit && durationValue.trim()
          ? `${durationValue.trim()} ${durationUnit}`
          : "";

    if (!normalizedDuration) {
      toast.error("Provide a duration value and unit, or mark it as Uncertain.");
      return;
    }

    const comparisonPayload = buildComparisonPayload(comparisonGroups);
    if (comparisonPayload.length === 0) {
      toast.error("Add at least one comparison with both sides populated.");
      return;
    }

    const normalizedCountries =
      selectedCountries.length > 0
        ? selectedCountries.map((country) => country.trim()).filter(Boolean)
        : ["Unclear"];

    const payload: StudyCreateDto = {
      shortName: shortName.trim(),
      status: statusOfStudy.trim(),
      countries: normalizedCountries,
      duration: normalizedDuration,
      numberParticipants: String(participantsValue),
      comparison: JSON.stringify(comparisonPayload),
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
        const updatedSide = [...group[side]];
        updatedSide.splice(index, 1);
        return {
          ...group,
          [side]: updatedSide,
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
              [side]: [...group[side], trimmed],
            }
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
    const matchIndex = group[side].findIndex(
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
      group[side].length > 0
        ? `${group[side].length} ${placeholderLabel}${
            group[side].length > 1 ? "s" : ""
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
          {group[side].map((value, index) => (
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
      </div>
    );
  };

  const computedDuration =
    durationUnit === "Uncertain"
      ? "Uncertain"
      : durationValue && durationUnit
        ? `${durationValue} ${durationUnit}`
        : "";
  const normalizedCountry =
    selectedCountries.length > 0 ? selectedCountries.join(", ") : "Unclear";
  const hasMultipleComparisonGroups = comparisonGroups.length > 1;
  const comparisonValid = hasValidComparisonGroups(comparisonGroups);

  const isSubmitDisabled =
    creatingStudy ||
    shortName.trim().length === 0 ||
    statusOfStudy.trim().length === 0 ||
    normalizedCountry.trim().length === 0 ||
    computedDuration.trim().length === 0 ||
    !comparisonValid ||
    numberOfParticipants.trim().length === 0;

  const handleOpenDialog = useCallback(() => {
    setAddStudyDialogOpen(true);
  }, [setAddStudyDialogOpen]);

  return (
    <Dialog open={addStudyDialogOpen} onOpenChange={setAddStudyDialogOpen}>
      <Button
        type="button"
        size="sm"
        className={`h-8 ${highlight ? "ai-new-study-glow" : ""}`}
        aria-haspopup="dialog"
        aria-expanded={addStudyDialogOpen}
        onClick={handleOpenDialog}
      >
        Add New Study
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
                  <SelectItem value="Closed">Closed</SelectItem>
                  <SelectItem value="Stopped early">Stopped early</SelectItem>
                  <SelectItem value="Open/Ongoing">Open/Ongoing</SelectItem>
                  <SelectItem value="Planned">Planned</SelectItem>
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
          <div className="grid gap-4 grid-cols-[7fr_3fr] items-start">
            <div className="space-y-2">
              <Label htmlFor="study-duration">Duration</Label>
              <Input
                id="study-duration"
                placeholder="12"
                type="number"
                min="0"
                value={durationValue}
                onChange={(event) => setDurationValue(event.target.value)}
                disabled={durationUnit === "Uncertain"}
                required={durationUnit !== "Uncertain"}
              />
            </div>
            <div className="space-y-2">
              <Label>Unit</Label>
              <Select
                value={durationUnit ?? undefined}
                onValueChange={(value) =>
                  setDurationUnit(value as StudyDurationUnit | undefined)
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Unit" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="hours">hours</SelectItem>
                  <SelectItem value="days">days</SelectItem>
                  <SelectItem value="weeks">weeks</SelectItem>
                  <SelectItem value="months">months</SelectItem>
                  <SelectItem value="years">years</SelectItem>
                  <SelectItem value="Uncertain">Uncertain</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="study-participants">Number of participants</Label>
            <Input
              id="study-participants"
              type="number"
              min="0"
              placeholder="0"
              value={numberOfParticipants}
              onChange={(event) => {
                const value = event.target.value;
                setNumberOfParticipants(value);
              }}
              required
            />
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
                    ? `min(${Math.round(
                        COMPARISON_PANEL_MAX_HEIGHT * 100
                      )}vh, ${COMPARISON_PANEL_MAX_PIXEL}px)`
                    : undefined,
                }}
              >
                {comparisonGroups.map((group, index) => (
                  <div
                    ref={index === 0 ? firstComparisonRef : undefined}
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
