import { useId, useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useStudySchema } from "@/hooks/use-study-schema";
import { useTagCatalogs } from "@/hooks/use-tag-catalog";
import { createOutcome } from "@/lib/comparisonUtils";
import type { OutcomeDraft, OutcomeRole, StudyDetails } from "@/types/comparisons";

const SEX_VALUES = ["female", "male", "other"];

const OUTCOME_ROLES: { value: OutcomeRole; label: string }[] = [
  { value: "primary", label: "Primary" },
  { value: "secondary", label: "Secondary" },
  { value: "other", label: "Other" },
];

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

interface ChipListProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder: string;
  // Offered while typing (the vocabulary of the field).
  options?: string[];
}

// A list of values as chips, with an input that adds one on Enter (or when it is left).
function ChipList({ label, values, onChange, placeholder, options = [] }: ChipListProps) {
  const id = useId();
  const [text, setText] = useState("");
  const commit = () => {
    const value = text.trim();
    setText("");
    if (!value || values.some((entry) => same(entry, value))) return;
    onChange([...values, options.find((option) => same(option, value)) ?? value]);
  };
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id} className="text-xs">{label}</Label>
      <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-input px-2 py-1">
        {values.map((value) => (
          <span
            key={value}
            className="inline-flex max-w-full items-center gap-1 rounded-full border border-border/60 bg-muted py-0.5 pl-2.5 pr-1 text-xs"
          >
            <span className="truncate">{value}</span>
            <button
              type="button"
              className="rounded-full p-0.5 text-muted-foreground hover:text-foreground"
              onClick={() => onChange(values.filter((entry) => entry !== value))}
              aria-label={`Remove ${value} from ${label}`}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          id={id}
          list={options.length > 0 ? `${id}-options` : undefined}
          className="h-6 min-w-[8rem] flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
          placeholder={placeholder}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              commit();
            } else if (event.key === "Backspace" && !text && values.length > 0) {
              onChange(values.slice(0, -1));
            }
          }}
        />
        {options.length > 0 && (
          <datalist id={`${id}-options`}>
            {options.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
        )}
      </div>
    </div>
  );
}

interface StudyDetailsFieldsProps {
  details: StudyDetails;
  onChange: (details: StudyDetails) => void;
  // Whether the form is shown (the vocabularies are loaded then).
  shown: boolean;
}

// Who the participants of the study are, its design and registration ids, and the interventions of no arm.
export function StudyPopulationFields({ details, onChange, shown }: StudyDetailsFieldsProps) {
  const vocabulary = useVocabulary(shown);
  const set = <K extends keyof StudyDetails>(key: K) => (value: StudyDetails[K]) => onChange({ ...details, [key]: value });
  return (
    <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2">
      <ChipList label="Conditions" values={details.conditions} onChange={set("conditions")} placeholder="Add a condition" options={vocabulary("condition")} />
      <div className="grid grid-cols-[1fr_1fr] items-start gap-2">
        <ChipList label="Sex" values={details.sex} onChange={set("sex")} placeholder="Add" options={SEX_VALUES} />
        <div className="space-y-1.5">
          <Label htmlFor="study-age" className="text-xs">Age</Label>
          <Input id="study-age" className="h-9 text-xs" placeholder="e.g. 18-65 years" value={details.age} onChange={(event) => set("age")(event.target.value)} />
        </div>
      </div>
      <ChipList label="Design" values={details.designs} onChange={set("designs")} placeholder="Add a design" options={vocabulary("design")} />
      <ChipList label="Trial IDs" values={details.trialIds} onChange={set("trialIds")} placeholder="e.g. NCT01234567" />
      {details.interventions.length > 0 && (
        <ChipList
          label="Interventions without an arm"
          values={details.interventions}
          onChange={set("interventions")}
          placeholder="Add an intervention"
          options={vocabulary("intervention")}
        />
      )}
    </div>
  );
}

// The outcomes of the study: a row each, with its role, what it measures and when.
export function StudyOutcomeFields({ details, onChange, shown }: StudyDetailsFieldsProps) {
  const vocabulary = useVocabulary(shown);
  const measures = vocabulary("measure");
  const listId = useId();
  const setOutcomes = (outcomes: OutcomeDraft[]) => onChange({ ...details, outcomes });
  const update = (id: string, changes: Partial<OutcomeDraft>) =>
    setOutcomes(details.outcomes.map((outcome) => (outcome.id === id ? { ...outcome, ...changes } : outcome)));
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-sm font-semibold">Outcomes</Label>
        <Button type="button" variant="ghost" size="sm" onClick={() => setOutcomes([...details.outcomes, createOutcome()])}>
          + Add outcome
        </Button>
      </div>
      {details.outcomes.length === 0 ? (
        <p className="text-xs text-muted-foreground">No outcomes.</p>
      ) : (
        <div className="space-y-1.5">
          {details.outcomes.map((outcome, index) => (
            <div key={outcome.id} className="flex items-center gap-1.5">
              <Select value={outcome.role} onValueChange={(value) => update(outcome.id, { role: value as OutcomeRole })}>
                <SelectTrigger size="sm" className="h-8 w-[112px] shrink-0 text-xs" aria-label={`Role of outcome ${index + 1}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {OUTCOME_ROLES.map((role) => (
                    <SelectItem key={role.value} value={role.value}>
                      {role.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                aria-label={`Measure of outcome ${index + 1}`}
                list={measures.length > 0 ? listId : undefined}
                className="h-8 min-w-0 flex-[3] text-xs"
                placeholder="What it measures, e.g. overall survival"
                value={outcome.measure}
                onChange={(event) => update(outcome.id, { measure: event.target.value })}
              />
              <Input
                aria-label={`Time point of outcome ${index + 1}`}
                className="h-8 min-w-0 flex-[2] text-xs"
                placeholder="When, e.g. at 4 weeks; at 12 weeks"
                value={outcome.timePoint}
                onChange={(event) => update(outcome.id, { timePoint: event.target.value })}
              />
              <Button
                variant="ghost"
                size="sm"
                type="button"
                className="h-8 w-8 shrink-0 p-0"
                onClick={() => setOutcomes(details.outcomes.filter((entry) => entry.id !== outcome.id))}
                aria-label={`Remove outcome ${index + 1}`}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
      {measures.length > 0 && (
        <datalist id={listId}>
          {measures.map((measure) => (
            <option key={measure} value={measure} />
          ))}
        </datalist>
      )}
    </div>
  );
}

// The tags of the category of a kind of value of the graph (e.g. the conditions of `condition`).
function useVocabulary(enabled: boolean): (kind: string) => string[] {
  const { schema } = useStudySchema();
  const catalogs = useTagCatalogs(enabled);
  return (kind) => {
    const category = schema?.graph.entities.find((entity) => entity.key === kind)?.value?.category;
    return catalogs.find((catalog) => catalog.category.key === category)?.values ?? [];
  };
}
