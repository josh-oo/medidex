import { Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useEligibilityCategories } from "@/hooks/use-eligibility-schema";
import { cn } from "@/lib/utils";
import type { EligibilityCriterion } from "@/types/apiDTOs";

const KIND_LABELS: Record<EligibilityCriterion["kind"], string> = { include: "Include", exclude: "Exclude" };
const KIND_CLASSES: Record<EligibilityCriterion["kind"], string> = {
  include: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300",
  exclude: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300",
};

/** A new criterion with an id that no other criterion of the list has. */
function newCriterion(criteria: EligibilityCriterion[], category: string): EligibilityCriterion {
  const taken = new Set(criteria.map((criterion) => criterion.id));
  let number = criteria.length + 1;
  while (taken.has(`c${number}`)) number += 1;
  return { id: `c${number}`, category, kind: "include", text: "" };
}

/** Whether the criteria can be saved: at least one, each with a text. */
export function criteriaComplete(criteria: EligibilityCriterion[]): boolean {
  return criteria.length > 0 && criteria.every((criterion) => criterion.text.trim().length > 0);
}

/** The criteria as they are sent: their texts trimmed. */
export function trimCriteria(criteria: EligibilityCriterion[]): EligibilityCriterion[] {
  return criteria.map((criterion) => ({ ...criterion, text: criterion.text.trim() }));
}

/** The criteria of a database to edit: one row each (include or exclude, its category, its text), one "Add criterion". */
export function EligibilityCriteriaEditor({
  criteria,
  onChange,
}: {
  criteria: EligibilityCriterion[];
  onChange: (criteria: EligibilityCriterion[]) => void;
}) {
  const categories = useEligibilityCategories();
  const update = (id: string, change: Partial<EligibilityCriterion>) =>
    onChange(criteria.map((criterion) => (criterion.id === id ? { ...criterion, ...change } : criterion)));
  const fallback = categories.at(-1)?.key ?? "other";

  return (
    <div className="rounded-lg border">
      {criteria.map((criterion, index) => (
        <div key={criterion.id} className={cn("flex items-start gap-1.5 px-2 py-1.5", index > 0 && "border-t")}>
          <Select value={criterion.kind} onValueChange={(kind) => update(criterion.id, { kind: kind as EligibilityCriterion["kind"] })}>
            <SelectTrigger
              size="sm"
              aria-label={`Criterion ${index + 1}: include or exclude`}
              className={cn("h-7 w-[5.5rem] shrink-0 gap-1 px-2 text-xs font-medium shadow-none", KIND_CLASSES[criterion.kind])}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(["include", "exclude"] as const).map((kind) => (
                <SelectItem key={kind} value={kind}>
                  {KIND_LABELS[kind]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={criterion.category} onValueChange={(category) => update(criterion.id, { category })}>
            <SelectTrigger size="sm" aria-label={`Criterion ${index + 1}: category`} className="h-7 w-[7.5rem] shrink-0 gap-1 px-2 text-xs shadow-none">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {categories.map((category) => (
                <SelectItem key={category.key} value={category.key} title={category.description}>
                  {category.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <textarea
            aria-label={`Criterion ${index + 1}`}
            value={criterion.text}
            onChange={(event) => update(criterion.id, { text: event.target.value })}
            placeholder="Criterion"
            rows={1}
            className="field-sizing-content min-h-7 min-w-0 flex-1 resize-none bg-transparent px-1 py-1 text-sm leading-snug outline-none placeholder:text-muted-foreground"
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0 text-muted-foreground"
            aria-label={`Remove criterion ${index + 1}`}
            onClick={() => onChange(criteria.filter((other) => other.id !== criterion.id))}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...criteria, newCriterion(criteria, fallback)])}
        className={cn(
          "flex h-9 w-full items-center gap-1.5 px-3 text-sm font-medium text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          criteria.length > 0 && "border-t"
        )}
      >
        <Plus className="h-3.5 w-3.5" />
        Add criterion
      </button>
    </div>
  );
}

/** The criteria of a database to read: one line each, with whether it includes or excludes and its category. */
export function EligibilityCriteriaList({ criteria }: { criteria: EligibilityCriterion[] }) {
  const categories = useEligibilityCategories();
  const label = (key: string) => categories.find((category) => category.key === key)?.label ?? key;

  return (
    <ul className="divide-y rounded-xl border">
      {criteria.map((criterion) => (
        <li key={criterion.id} className="flex items-start gap-2 px-3 py-2 text-sm">
          <span className={cn("mt-0.5 w-16 shrink-0 rounded border px-1.5 text-center text-xs font-medium leading-5", KIND_CLASSES[criterion.kind])}>
            {KIND_LABELS[criterion.kind]}
          </span>
          <span className="mt-0.5 w-20 shrink-0 text-xs leading-5 text-muted-foreground">{label(criterion.category)}</span>
          <span className="min-w-0 whitespace-pre-line">{criterion.text}</span>
        </li>
      ))}
    </ul>
  );
}
