import { Ban, Check, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useEligibilityCategories } from "@/hooks/use-eligibility-schema";
import { colorClasses } from "@/lib/colors";
import { cn } from "@/lib/utils";
import type { EligibilityCategoryDto, EligibilityCriterion } from "@/types/apiDTOs";

const KIND_LABELS: Record<EligibilityCriterion["kind"], string> = { include: "Include", exclude: "Exclude" };
const KIND_ICONS: Record<EligibilityCriterion["kind"], typeof Check> = { include: Check, exclude: Ban };
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

/** The categories by their element of PICO (or the study), in their order: the element first, then its relations. */
function groupsOf(categories: EligibilityCategoryDto[]): [string, EligibilityCategoryDto[]][] {
  const groups = new Map<string, EligibilityCategoryDto[]>();
  for (const category of categories) groups.set(category.path[0], [...(groups.get(category.path[0]) ?? []), category]);
  return [...groups];
}

/** The path of a category in the ontology ("Population → Conditions"), what it is about in its color. */
function CategoryPath({ category, fallback }: { category: EligibilityCategoryDto | undefined; fallback: string }) {
  if (!category) return <span>{fallback}</span>;
  return (
    <span className="truncate">
      {category.path.map((part, index) => (
        <span key={index} className={cn(index === category.path.length - 1 && colorClasses(category.color).accent)}>
          {index > 0 && <span className="px-1 text-muted-foreground/70">→</span>}
          {part}
        </span>
      ))}
    </span>
  );
}

/** Whether a criterion includes or excludes, as a square; a button that switches it while it is edited. */
function KindBadge({ kind, onToggle, label }: { kind: EligibilityCriterion["kind"]; onToggle?: () => void; label?: string }) {
  const Icon = KIND_ICONS[kind];
  const className = cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-md border", KIND_CLASSES[kind]);
  if (!onToggle) {
    return (
      <span title={KIND_LABELS[kind]} className={className}>
        <Icon className="h-3.5 w-3.5" />
        <span className="sr-only">{KIND_LABELS[kind]}</span>
      </span>
    );
  }
  const other = kind === "include" ? "exclude" : "include";
  return (
    <button
      type="button"
      aria-label={`${label}: ${KIND_LABELS[kind]}, switch to ${KIND_LABELS[other].toLowerCase()}`}
      title={`${KIND_LABELS[kind]} (click to ${KIND_LABELS[other].toLowerCase()})`}
      onClick={onToggle}
      className={cn(className, "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
    >
      <Icon className="h-3.5 w-3.5" />
    </button>
  );
}

/** The criteria of a database to edit: one row each (whether it includes or excludes; what it is about, as its path from
 * its element of PICO, above its text), one "Add criterion". */
export function EligibilityCriteriaEditor({
  criteria,
  onChange,
}: {
  criteria: EligibilityCriterion[];
  onChange: (criteria: EligibilityCriterion[]) => void;
}) {
  const categories = useEligibilityCategories();
  const groups = groupsOf(categories);
  const update = (id: string, change: Partial<EligibilityCriterion>) =>
    onChange(criteria.map((criterion) => (criterion.id === id ? { ...criterion, ...change } : criterion)));
  // A new criterion is about what the last one is about, until another is chosen.
  const fallback = criteria.at(-1)?.category ?? categories[0]?.key ?? "population";

  return (
    <div className="rounded-lg border">
      {criteria.map((criterion, index) => {
        const category = categories.find((candidate) => candidate.key === criterion.category);
        return (
          <div key={criterion.id} className={cn("flex items-start gap-2 px-2 py-2", index > 0 && "border-t")}>
            <KindBadge
              kind={criterion.kind}
              label={`Criterion ${index + 1}`}
              onToggle={() => update(criterion.id, { kind: criterion.kind === "include" ? "exclude" : "include" })}
            />
            <div className="min-w-0 flex-1">
              <Select value={criterion.category} onValueChange={(key) => update(criterion.id, { category: key })}>
                <SelectTrigger
                  size="sm"
                  aria-label={`Criterion ${index + 1}: what it is about`}
                  title={category?.description}
                  className="h-5 max-w-full gap-1 border-0 bg-transparent px-1 py-0 text-xs font-medium shadow-none hover:bg-muted data-[size=sm]:h-5 dark:bg-transparent [&_svg]:size-3"
                >
                  <SelectValue>
                    <CategoryPath category={category} fallback={criterion.category} />
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {groups.map(([element, members]) => (
                    <SelectGroup key={element}>
                      {members.map((member) => (
                        <SelectItem
                          key={member.key}
                          value={member.key}
                          title={member.description}
                          className={cn(member.path.length === 1 ? "font-medium" : "pl-6")}
                        >
                          {member.path.at(-1)}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  ))}
                </SelectContent>
              </Select>
              <textarea
                aria-label={`Criterion ${index + 1}`}
                value={criterion.text}
                onChange={(event) => update(criterion.id, { text: event.target.value })}
                placeholder="Criterion"
                rows={1}
                className="field-sizing-content block min-h-6 w-full resize-none bg-transparent px-1 text-sm leading-snug outline-none placeholder:text-muted-foreground"
              />
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0 text-muted-foreground"
              aria-label={`Remove criterion ${index + 1}`}
              onClick={() => onChange(criteria.filter((candidate) => candidate.id !== criterion.id))}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        );
      })}
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

/** The criteria of a database to read: one line each, with whether it includes or excludes and what it is about. */
export function EligibilityCriteriaList({ criteria }: { criteria: EligibilityCriterion[] }) {
  const categories = useEligibilityCategories();

  return (
    <ul className="divide-y rounded-xl border">
      {criteria.map((criterion) => {
        const category = categories.find((candidate) => candidate.key === criterion.category);
        return (
          <li key={criterion.id} className="flex items-start gap-2 px-3 py-2 text-sm">
            <KindBadge kind={criterion.kind} />
            <div className="min-w-0">
              <div className="flex text-xs font-medium leading-5" title={category?.description}>
                <CategoryPath category={category} fallback={criterion.category} />
              </div>
              <p className="whitespace-pre-line">{criterion.text}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
