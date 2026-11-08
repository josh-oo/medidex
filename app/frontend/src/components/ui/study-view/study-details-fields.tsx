import { useEffect, useId, useRef, useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useStudySchema } from "@/hooks/use-study-schema";
import { useTagCatalogs } from "@/hooks/use-tag-catalog";
import { createOutcome } from "@/lib/comparisonUtils";
import { cn } from "@/lib/utils";
import type { OutcomeDraft, StudyDetails } from "@/types/comparisons";

const SEX_VALUES = ["female", "male", "other"];

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();

interface ChipListProps {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
  placeholder: string;
  // Offered while typing (the vocabulary of the field).
  options?: string[];
  // Only the options can be added (e.g. countries).
  strict?: boolean;
  className?: string;
}

// A list of values as chips in one line, with an input that adds one on Enter (or when it is left). More chips than fit
// scroll sideways instead of making the field taller; one added scrolls the line to its end, where the input is.
export function ChipList({ label, values, onChange, placeholder, options = [], strict = false, className }: ChipListProps) {
  const id = useId();
  const [text, setText] = useState("");
  const lineRef = useRef<HTMLDivElement>(null);
  const count = values.length;
  const previousCount = useRef(count);
  useEffect(() => {
    if (count > previousCount.current && lineRef.current) lineRef.current.scrollLeft = lineRef.current.scrollWidth;
    previousCount.current = count;
  }, [count]);
  const commit = () => {
    const value = text.trim();
    setText("");
    const option = options.find((entry) => same(entry, value));
    if (!value || values.some((entry) => same(entry, value)) || (strict && !option)) return;
    onChange([...values, option ?? value]);
  };
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id} className="text-xs">{label}</Label>
      <div
        ref={lineRef}
        className="flex h-9 items-center gap-1.5 overflow-x-auto overflow-y-hidden rounded-md border border-input px-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {values.map((value) => (
          <span
            key={value}
            title={value}
            className="inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border border-border/60 bg-muted py-0.5 pl-2.5 pr-1 text-xs"
          >
            <span>{value}</span>
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
          className="h-6 w-0 min-w-[6rem] flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
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

// The sexes of the participants as one segmented control, a toggle each; a value of the graph that is none of them
// gets its own toggle.
export function SexToggles({
  values,
  onChange,
  className,
}: {
  values: string[];
  onChange: (values: string[]) => void;
  className?: string;
}) {
  const id = useId();
  const options = [...SEX_VALUES, ...values.filter((value) => !SEX_VALUES.some((option) => same(option, value)))];
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label id={id} className="text-xs">Sex</Label>
      <ToggleGroup
        className="w-full"
        type="multiple"
        variant="outline"
        aria-labelledby={id}
        value={options.filter((option) => values.some((value) => same(value, option)))}
        onValueChange={onChange}
      >
        {options.map((option) => (
          <ToggleGroupItem key={option} value={option} className="h-9 flex-1 px-2.5 text-xs font-normal">
            {option}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
    </div>
  );
}

interface StudyDetailsFieldsProps {
  details: StudyDetails;
  onChange: (details: StudyDetails) => void;
  // Whether the form is shown (the vocabularies are loaded then).
  shown: boolean;
}

// The outcomes of the study, two to a row: what each measures, and below it, smaller, its time points (a registry
// record's primary or secondary one is marked so; the form adds outcomes without a role, as the extraction does).
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
        <div className="grid grid-cols-1 gap-x-4 gap-y-1 @xl:grid-cols-2">
          {details.outcomes.map((outcome, index) => (
            <div key={outcome.id} className="group min-w-0 rounded-md px-1 py-1 hover:bg-muted/40">
              <div className="flex items-center gap-1">
                {outcome.role !== "other" && (
                  <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase text-muted-foreground">
                    {outcome.role === "primary" ? "Primary" : "Secondary"}
                  </span>
                )}
                <input
                  aria-label={`Measure of outcome ${index + 1}`}
                  list={measures.length > 0 ? listId : undefined}
                  className="h-7 min-w-0 flex-1 rounded-sm bg-transparent px-1 text-sm font-medium outline-none placeholder:font-normal placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
                  placeholder="What it measures, e.g. overall survival"
                  value={outcome.measure}
                  onChange={(event) => update(outcome.id, { measure: event.target.value })}
                />
                <button
                  type="button"
                  className="shrink-0 rounded-full p-1 text-muted-foreground opacity-60 hover:text-foreground group-hover:opacity-100"
                  onClick={() => setOutcomes(details.outcomes.filter((entry) => entry.id !== outcome.id))}
                  aria-label={`Remove outcome ${index + 1}`}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
              <TimePoints
                label={`outcome ${index + 1}`}
                values={outcome.timePoints}
                onChange={(timePoints) => update(outcome.id, { timePoints })}
              />
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

// The time points of an outcome as small chips under it, with a field that adds one on Enter (or when it is left).
function TimePoints({ label, values, onChange }: { label: string; values: string[]; onChange: (values: string[]) => void }) {
  const [text, setText] = useState("");
  const commit = () => {
    const value = text.trim();
    setText("");
    if (value && !values.some((entry) => same(entry, value))) onChange([...values, value]);
  };
  return (
    <div className="flex flex-wrap items-center gap-1 pl-1">
      {values.map((value) => (
        <span
          key={value}
          className="inline-flex max-w-full items-center gap-0.5 rounded-full bg-muted py-px pl-2 pr-0.5 text-[11px] text-muted-foreground"
        >
          <span className="truncate">{value}</span>
          <button
            type="button"
            className="rounded-full p-0.5 hover:text-foreground"
            onClick={() => onChange(values.filter((entry) => entry !== value))}
            aria-label={`Remove ${value} from the time points of ${label}`}
          >
            <X className="h-2.5 w-2.5" />
          </button>
        </span>
      ))}
      <input
        aria-label={`Add a time point to ${label}`}
        className="h-5 w-0 min-w-[6rem] flex-1 bg-transparent px-1 text-[11px] text-muted-foreground outline-none placeholder:text-muted-foreground/60"
        placeholder="+ time point"
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
    </div>
  );
}

// The tags of the category of a kind of value of the graph (e.g. the conditions of `condition`).
export function useVocabulary(enabled: boolean): (kind: string) => string[] {
  const { schema } = useStudySchema();
  const catalogs = useTagCatalogs(enabled);
  return (kind) => {
    const category = schema?.graph.entities.find((entity) => entity.key === kind)?.value?.category;
    return catalogs.find((catalog) => catalog.category.key === category)?.values ?? [];
  };
}
