import { useState, type ReactNode } from "react";
import { Plus, X } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { useStudyFieldValues } from "@/hooks/use-study-schema";
import { matchValues, type TagCatalog } from "@/hooks/use-tag-catalog";
import { colorClasses } from "@/lib/colors";
import { iconByName } from "@/lib/icons";
import { sameFilter, type StudyFilter } from "@/lib/study-filters";
import { cn } from "@/lib/utils";

const MAX_OPTIONS = 50;

interface StudyFilterPanelProps {
  catalogs: TagCatalog[];
  filters: StudyFilter[];
  /** The fields whose values must all match (the others: any of them). */
  allFields: string[];
  onToggleAll: (field: string) => void;
  onAdd: (filter: StudyFilter) => void;
  onRemove: (filter: StudyFilter) => void;
}

/**
 * The filters of the search: one block per tag category of the study schema, plus the status. A block with two values
 * or more can match any or all of them; the blocks must all match. The filters are controls: neutral chips with a dot
 * in the colour of their category, unlike the coloured tags of the results (the content).
 */
export function StudyFilterPanel({ catalogs, filters, allFields, onToggleAll, onAdd, onRemove }: StudyFilterPanelProps) {
  const statuses = useStudyFieldValues("status");

  return (
    <div className="min-w-0 divide-y divide-border/70 text-sm">
      {catalogs.map(({ category, values }) => {
        const active = filters.filter((filter) => filter.field === category.searchField);
        const Icon = iconByName(category.icon);
        const colors = colorClasses(category.color);
        const add = (
          <AddFilter
            label={category.label}
            values={values}
            exclude={active.map((filter) => filter.value)}
            onPick={(value) => onAdd({ field: category.searchField, value })}
            compact={active.length === 0}
          />
        );

        return (
          <FilterBlock
            key={category.key}
            icon={<Icon className={cn("h-3.5 w-3.5", colors.accent)} aria-hidden />}
            label={category.label}
            control={
              active.length >= 2 ? (
                <MatchSwitch all={allFields.includes(category.searchField)} onToggle={() => onToggleAll(category.searchField)} />
              ) : active.length === 0 ? (
                add
              ) : null
            }
          >
            {active.length > 0 && (
              <>
                <ul className="flex min-w-0 flex-wrap gap-1.5">
                  {active.map((filter) => (
                    // A chip never grows wider than the column; a long value is cut off (in full on hover).
                    <li key={filter.value} className="min-w-0 max-w-full">
                      <FilterChip filter={filter} label={filter.value} dotClassName={colors.accent} onRemove={onRemove} />
                    </li>
                  ))}
                </ul>
                {add}
              </>
            )}
          </FilterBlock>
        );
      })}

      {statuses.length > 0 && (
        <FilterBlock label="Status">
          <div className="space-y-1.5">
            {statuses.map((status) => {
              const filter = { field: "status", value: status };
              const checked = filters.some((active) => sameFilter(active, filter));
              return (
                <label key={status} className="flex cursor-pointer items-center gap-2 capitalize">
                  <Checkbox checked={checked} onCheckedChange={() => (checked ? onRemove(filter) : onAdd(filter))} />
                  {status}
                </label>
              );
            })}
          </div>
        </FilterBlock>
      )}
    </div>
  );
}

function FilterBlock({
  icon,
  label,
  control,
  children,
}: {
  icon?: ReactNode;
  label: string;
  control?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <section className="min-w-0 space-y-2 py-3 first:pt-0">
      <div className="flex min-h-7 items-center gap-2">
        {icon}
        <h3 className="min-w-0 flex-1 truncate font-medium">{label}</h3>
        {control}
      </div>
      {children}
    </section>
  );
}

/** Whether a block matches any or all of its values. */
export function MatchSwitch({ all, onToggle }: { all: boolean; onToggle: () => void }) {
  return (
    <div role="radiogroup" aria-label="Match" className="flex shrink-0 rounded-md bg-muted p-0.5 text-[11px]">
      {[false, true].map((option) => (
        <button
          key={String(option)}
          type="button"
          role="radio"
          aria-checked={all === option}
          onClick={() => all !== option && onToggle()}
          className={cn(
            "rounded px-2 py-0.5 font-medium transition-colors",
            all === option ? "bg-card text-foreground shadow-xs" : "text-muted-foreground hover:text-foreground"
          )}
        >
          {option ? "All" : "Any"}
        </button>
      ))}
    </div>
  );
}

/** A chosen filter; `dotClassName` (a text colour) marks its category. */
export function FilterChip({
  filter,
  label,
  dotClassName,
  onRemove,
}: {
  filter: StudyFilter;
  label: string;
  dotClassName?: string;
  onRemove: (filter: StudyFilter) => void;
}) {
  return (
    <span
      title={label}
      className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-full border bg-card py-0.5 pl-2 pr-1 text-xs text-foreground shadow-xs"
    >
      {dotClassName && <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full bg-current", dotClassName)} aria-hidden />}
      <span className="min-w-0 truncate">{label}</span>
      <button
        type="button"
        aria-label={`Remove ${label}`}
        onClick={() => onRemove(filter)}
        className="grid h-4 w-4 shrink-0 place-items-center rounded-full text-muted-foreground hover:bg-primary/10 hover:text-primary"
      >
        <X className="h-3 w-3" />
      </button>
    </span>
  );
}

function AddFilter({
  label,
  values,
  exclude,
  onPick,
  compact,
}: {
  label: string;
  values: string[];
  exclude: string[];
  onPick: (value: string) => void;
  /** Only the plus, in the header of an empty block. */
  compact: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const options = matchValues(values, text, MAX_OPTIONS).filter((value) => !exclude.includes(value));

  const pick = (value: string) => {
    onPick(value);
    setText("");
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={`Add ${label.toLowerCase()}`}
          className={cn(
            "flex shrink-0 items-center gap-1 rounded-md text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
            compact ? "h-7 px-1.5" : "-ml-0.5 h-6 px-1"
          )}
        >
          <Plus className="h-3.5 w-3.5" aria-hidden />
          {compact ? "Add" : "Add another"}
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-72 overflow-hidden rounded-2xl border bg-popover p-0 shadow-lg" sideOffset={6}>
        <Command shouldFilter={false}>
          <CommandInput value={text} onValueChange={setText} placeholder={`Search ${label.toLowerCase()}…`} />
          <CommandList className="max-h-64 overflow-y-auto">
            <CommandEmpty className="py-4 text-center text-xs text-muted-foreground">Nothing found.</CommandEmpty>
            {options.length > 0 && (
              <CommandGroup>
                {options.map((value) => (
                  <CommandItem key={value} value={value} onSelect={() => pick(value)}>
                    <span className="truncate">{value}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {text.trim() && !options.some((value) => value.toLowerCase() === text.trim().toLowerCase()) && (
              <CommandGroup>
                <CommandItem value={`__text__${text}`} onSelect={() => pick(text.trim())}>
                  <span className="truncate">Contains &ldquo;{text.trim()}&rdquo;</span>
                </CommandItem>
              </CommandGroup>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
