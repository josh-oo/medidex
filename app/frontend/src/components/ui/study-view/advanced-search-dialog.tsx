import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  BookOpen,
  ChevronDown,
  CircleDot,
  FolderPlus,
  Hash,
  Plus,
  SlidersHorizontal,
  UserRound,
  X,
  type LucideIcon,
} from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Highlight } from "@/components/search/study-search-bar";
import { useStudyFieldValues, useStudySchema } from "@/hooks/use-study-schema";
import { matchValues, useTagCatalogs } from "@/hooks/use-tag-catalog";
import { colorClasses } from "@/lib/colors";
import { iconByName } from "@/lib/icons";
import { cn } from "@/lib/utils";

// The fields of the backend's advanced-search grammar (src/utils/query_parser.py and
// StudyRepository.search_studies_advanced): the search field of every tag category of the study
// schema, plus the study's own fields below. Field names are matched case-insensitively there.
interface FieldOption {
  key: string;
  label: string;
  icon: LucideIcon;
  /** Classes of the icon tile (from the colour of the tag category). */
  tile: string;
  accent: string;
  /** The values offered while typing; null for a free text. */
  values: string[] | null;
  placeholder: string;
}

const STUDY_FIELDS = [
  { key: "name", label: "Study name", icon: BookOpen, placeholder: "e.g. Steiner 1995" },
  { key: "trialId", label: "Trial ID", icon: Hash, placeholder: "e.g. NCT01234567" },
  { key: "author", label: "Author", icon: UserRound, placeholder: "e.g. Smith" },
] as const;

const NEUTRAL = colorClasses("slate");
const MAX_OPTIONS = 50;

type Operator = "AND" | "OR";

// A bracket-group builder: mirrors the backend's Comparison/AndGroup/OrGroup tree
// (src/utils/query_parser.py) - a group's `operator` applies to all of its direct `children`;
// mixing AND and OR at one level means nesting a sub-group, same as the backend's structured
// form. This is what gets rendered into the parenthesized string the REST API's advanced search
// takes (buildQuery below).
interface ConditionNode {
  kind: "condition";
  id: string;
  /** A field of the grammar; empty until one is chosen, then the default field (see `fieldOf`). */
  field: string;
  value: string;
}

interface GroupNode {
  kind: "group";
  id: string;
  operator: Operator;
  children: RowNode[];
}

type RowNode = ConditionNode | GroupNode;

const createNodeId = () => `qnode-${Math.random().toString(36).slice(2, 9)}`;

const createEmptyCondition = (): ConditionNode => ({
  kind: "condition",
  id: createNodeId(),
  field: "",
  value: "",
});

const createEmptyGroup = (operator: Operator = "AND"): GroupNode => ({
  kind: "group",
  id: createNodeId(),
  operator,
  children: [createEmptyCondition()],
});

const isRowNode = (value: unknown): value is RowNode => {
  if (!value || typeof value !== "object") return false;
  const node = value as Record<string, unknown>;
  if (typeof node.id !== "string") return false;
  if (node.kind === "condition") {
    return typeof node.field === "string" && typeof node.value === "string";
  }
  if (node.kind === "group") {
    return (
      (node.operator === "AND" || node.operator === "OR") &&
      Array.isArray(node.children) &&
      node.children.every(isRowNode)
    );
  }
  return false;
};

const isGroupNode = (value: unknown): value is GroupNode =>
  isRowNode(value) && (value as RowNode).kind === "group";

const updateNodeById = (node: RowNode, id: string, updater: (node: RowNode) => RowNode): RowNode => {
  if (node.id === id) return updater(node);
  if (node.kind !== "group") return node;
  return { ...node, children: node.children.map((child) => updateNodeById(child, id, updater)) };
};

const removeNodeById = (node: GroupNode, id: string): GroupNode => ({
  ...node,
  children: node.children
    .filter((child) => child.id !== id)
    .map((child) => (child.kind === "group" ? removeNodeById(child, id) : child)),
});

const addChildToGroup = (node: GroupNode, groupId: string, child: RowNode): GroupNode => {
  if (node.id === groupId) {
    return { ...node, children: [...node.children, child] };
  }
  return {
    ...node,
    children: node.children.map((existing) =>
      existing.kind === "group" ? addChildToGroup(existing, groupId, child) : existing
    ),
  };
};

// Quotes a value for the advanced-search grammar so literal whitespace/AND/OR/")" text
// in it can't be mistaken for grammar syntax - see query_parser.py's QuotedString usage.
// The grammar has no escape mechanism, so a value containing both quote characters falls
// back to being left unquoted (best effort for that rare case).
const quoteValue = (value: string): string => {
  const trimmed = value.trim();
  if (!trimmed.includes('"')) {
    return `"${trimmed}"`;
  }
  if (!trimmed.includes("'")) {
    return `'${trimmed}'`;
  }
  return trimmed;
};

// Renders a node into the parenthesized string grammar. A group with 2+ filled
// children is always wrapped in parentheses when nested (never at the root) so
// precedence is always explicit - matching how the structured form has no precedence
// ambiguity to begin with. A group left with exactly one filled child (after empty
// conditions/groups are dropped) unwraps to that child directly, with no redundant
// parentheses.
const renderNode = (node: RowNode, isRoot: boolean, defaultField: string): string | null => {
  if (node.kind === "condition") {
    const trimmed = node.value.trim();
    if (!trimmed) return null;
    return `${node.field || defaultField}==${quoteValue(trimmed)}`;
  }

  const parts = node.children
    .map((child) => renderNode(child, false, defaultField))
    .filter((part): part is string => part !== null);

  if (parts.length === 0) return null;
  if (parts.length === 1) return parts[0];

  const joined = parts.join(` ${node.operator} `);
  return isRoot ? joined : `(${joined})`;
};

const buildQuery = (root: GroupNode, defaultField: string): string =>
  renderNode(root, true, defaultField) ?? "";

const STORAGE_KEY = "medidex.advancedSearchQuery.v1";

const loadPersistedRoot = (): GroupNode => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (isGroupNode(parsed)) return parsed;
    }
  } catch {
    // Ignore unreadable/corrupt storage - fall through to a fresh empty group.
  }
  return createEmptyGroup();
};

/** The fields of the grammar: the tag categories of the study schema (with their vocabulary), the study's own fields
 * and the status. */
function useFieldOptions(enabled: boolean): FieldOption[] {
  const { schema } = useStudySchema();
  const catalogs = useTagCatalogs(enabled);
  const statuses = useStudyFieldValues("status");

  return useMemo(() => {
    const tags: FieldOption[] = (schema?.tags ?? []).map((category) => {
      const colors = colorClasses(category.color);
      return {
        key: category.searchField,
        label: category.label,
        icon: iconByName(category.icon),
        tile: colors.bg,
        accent: colors.accent,
        values: catalogs.find((catalog) => catalog.category.key === category.key)?.values ?? [],
        placeholder: `Search ${category.label.toLowerCase()}…`,
      };
    });
    const study: FieldOption[] = STUDY_FIELDS.map((field) => ({
      ...field,
      tile: NEUTRAL.bg,
      accent: NEUTRAL.accent,
      values: null,
    }));
    const status: FieldOption = {
      key: "status",
      label: "Status",
      icon: CircleDot,
      tile: NEUTRAL.bg,
      accent: NEUTRAL.accent,
      values: statuses,
      placeholder: "Choose a status…",
    };
    return [...tags, ...study, status];
  }, [schema, catalogs, statuses]);
}

/** A field the schema no longer has (e.g. from a query kept in the browser) is shown by its name. */
const unknownField = (key: string): FieldOption => ({
  key,
  label: key,
  icon: CircleDot,
  tile: NEUTRAL.bg,
  accent: NEUTRAL.accent,
  values: null,
  placeholder: "Value…",
});

function FieldIcon({ field, className }: { field: FieldOption; className?: string }) {
  const Icon = field.icon;
  return (
    <span className={cn("grid h-6 w-6 shrink-0 place-items-center rounded-md", field.tile, className)}>
      <Icon className={cn("h-3.5 w-3.5", field.accent)} aria-hidden />
    </span>
  );
}

interface ConditionRowProps {
  node: ConditionNode;
  fields: FieldOption[];
  defaultField: string;
  onFieldChange: (field: string) => void;
  onValueChange: (value: string) => void;
  onRemove: () => void;
  onSubmit: () => void;
}

/** One condition as a pill like the search bar of the start page: the field, the value with suggestions from the
 * vocabulary of the field, and a remove button. */
function ConditionRow({
  node,
  fields,
  defaultField,
  onFieldChange,
  onValueChange,
  onRemove,
  onSubmit,
}: ConditionRowProps) {
  const fieldKey = node.field || defaultField;
  const field = fields.find((candidate) => candidate.key === fieldKey) ?? unknownField(fieldKey);
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const options = useMemo(() => {
    if (!field.values) return [];
    const matches = matchValues(field.values, node.value, MAX_OPTIONS);
    // The value already chosen needs no suggestion.
    return matches.length === 1 && matches[0].toLowerCase() === node.value.trim().toLowerCase() ? [] : matches;
  }, [field.values, node.value]);
  const showList = open && options.length > 0;

  const pick = (value: string) => {
    onValueChange(value);
    setOpen(false);
    setActiveIndex(-1);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown" && options.length > 0) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((index) => (index + 1) % options.length);
    } else if (event.key === "ArrowUp" && options.length > 0) {
      event.preventDefault();
      setActiveIndex((index) => (index <= 0 ? options.length - 1 : index - 1));
    } else if (event.key === "Escape" && showList) {
      // The first Escape closes the suggestions, the next one the dialog.
      event.preventDefault();
      event.stopPropagation();
      setOpen(false);
      setActiveIndex(-1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (showList && activeIndex >= 0) pick(options[activeIndex]);
      else onSubmit();
    }
  };

  return (
    <Popover open={showList} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <div className="flex min-w-0 items-center gap-1 rounded-full border bg-card p-1 shadow-xs transition-shadow focus-within:ring-2 focus-within:ring-ring/40">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={`Field: ${field.label}`}
                className="flex h-8 max-w-[45%] shrink-0 items-center gap-1.5 rounded-full bg-muted/70 pl-1 pr-2 text-sm font-medium transition-colors hover:bg-muted"
              >
                <FieldIcon field={field} className="rounded-full" />
                <span className="hidden truncate @sm:inline">{field.label}</span>
                <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="start"
              sideOffset={6}
              className="max-h-80 w-56 rounded-2xl p-1.5"
              onCloseAutoFocus={(event) => {
                // Straight on to the value.
                event.preventDefault();
                inputRef.current?.focus();
              }}
            >
              {fields.map((option, index) => {
                const startsStudy = option.key === STUDY_FIELDS[0].key && index > 0;
                return (
                  <div key={option.key}>
                    {startsStudy && <DropdownMenuSeparator />}
                    {(index === 0 || startsStudy) && (
                      <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                        {startsStudy ? "Study" : "Tags"}
                      </DropdownMenuLabel>
                    )}
                    <DropdownMenuItem
                      className={cn("gap-2.5 rounded-xl", option.key === fieldKey && "bg-muted")}
                      onSelect={() => option.key !== fieldKey && onFieldChange(option.key)}
                    >
                      <FieldIcon field={option} />
                      <span className="truncate">{option.label}</span>
                    </DropdownMenuItem>
                  </div>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>

          <input
            ref={inputRef}
            type="text"
            role={field.values ? "combobox" : undefined}
            aria-label={`${field.label} value`}
            aria-expanded={field.values ? showList : undefined}
            aria-autocomplete={field.values ? "list" : undefined}
            value={node.value}
            placeholder={field.placeholder}
            onChange={(event) => {
              onValueChange(event.target.value);
              setOpen(true);
              setActiveIndex(-1);
            }}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            onKeyDown={handleKeyDown}
            className="h-8 min-w-0 flex-1 bg-transparent px-1.5 text-sm outline-none placeholder:text-muted-foreground"
          />

          <button
            type="button"
            aria-label="Remove condition"
            onClick={onRemove}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </PopoverAnchor>
      <PopoverContent
        align="start"
        sideOffset={6}
        // The suggestions are as wide as the row; the focus stays in the input.
        className="w-(--radix-popover-trigger-width) rounded-2xl border bg-popover p-1.5 shadow-lg"
        onOpenAutoFocus={(event) => event.preventDefault()}
        onInteractOutside={(event) => {
          if (event.target === inputRef.current) event.preventDefault();
        }}
      >
        <ul role="listbox" aria-label="Suggestions" className="max-h-64 overflow-y-auto overscroll-contain">
          {options.map((option, index) => (
            <li
              key={option}
              role="option"
              aria-selected={index === activeIndex}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => pick(option)}
              onMouseEnter={() => setActiveIndex(index)}
              className={cn(
                "flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2 text-sm",
                index === activeIndex && "bg-muted"
              )}
            >
              <FieldIcon field={field} />
              <span className="min-w-0 flex-1 truncate">
                <Highlight text={option} terms={[node.value]} />
              </span>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

/** The word between two rows of a group; switches the group between all and any, like the query summary of the start
 * page. */
function Connector({ operator, onToggle }: { operator: Operator; onToggle: () => void }) {
  return (
    <div className="flex items-center gap-2 pl-5">
      <span className="h-3 w-px bg-border" aria-hidden />
      <button
        type="button"
        onClick={onToggle}
        title={`Switch to “${operator === "AND" ? "or" : "and"}”`}
        className="border-b border-dashed border-foreground/30 text-xs font-medium leading-4 text-muted-foreground hover:border-foreground hover:text-foreground"
      >
        {operator === "AND" ? "and" : "or"}
      </button>
    </div>
  );
}

interface GroupEditorProps {
  node: GroupNode;
  isRoot: boolean;
  fields: FieldOption[];
  defaultField: string;
  onUpdate: (id: string, updater: (node: RowNode) => RowNode) => void;
  onRemove: (id: string) => void;
  onAddCondition: (groupId: string) => void;
  onAddGroup: (groupId: string) => void;
  onSubmit: () => void;
}

function GroupEditor({
  node,
  isRoot,
  fields,
  defaultField,
  onUpdate,
  onRemove,
  onAddCondition,
  onAddGroup,
  onSubmit,
}: GroupEditorProps) {
  const toggleOperator = () =>
    onUpdate(node.id, (current) => ({ ...current, operator: node.operator === "AND" ? "OR" : "AND" }));

  return (
    <div className={cn("space-y-2", !isRoot && "rounded-2xl border border-dashed bg-muted/40 p-3")}>
      <div>
        {node.children.map((child, index) => (
          <div key={child.id}>
            {index > 0 && <Connector operator={node.operator} onToggle={toggleOperator} />}
            {child.kind === "condition" ? (
              <ConditionRow
                node={child}
                fields={fields}
                defaultField={defaultField}
                onFieldChange={(field) => onUpdate(child.id, (current) => ({ ...current, field, value: "" }))}
                onValueChange={(value) => onUpdate(child.id, (current) => ({ ...current, value }))}
                onRemove={() => onRemove(child.id)}
                onSubmit={onSubmit}
              />
            ) : (
              <GroupEditor
                node={child}
                isRoot={false}
                fields={fields}
                defaultField={defaultField}
                onUpdate={onUpdate}
                onRemove={onRemove}
                onAddCondition={onAddCondition}
                onAddGroup={onAddGroup}
                onSubmit={onSubmit}
              />
            )}
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 pt-1">
        <AddButton icon={Plus} label="Condition" onClick={() => onAddCondition(node.id)} />
        <AddButton icon={FolderPlus} label="Group" onClick={() => onAddGroup(node.id)} />
        {!isRoot && (
          <button
            type="button"
            onClick={() => onRemove(node.id)}
            className="ml-auto flex h-7 items-center gap-1 rounded-full px-2.5 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" aria-hidden />
            Remove group
          </button>
        )}
      </div>
    </div>
  );
}

function AddButton({ icon: Icon, label, onClick }: { icon: LucideIcon; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-7 items-center gap-1 rounded-full border border-dashed px-2.5 text-xs text-muted-foreground transition-colors hover:border-solid hover:bg-card hover:text-foreground"
    >
      <Icon className="h-3.5 w-3.5" aria-hidden />
      {label}
    </button>
  );
}

interface AdvancedSearchDialogProps {
  onSearch: (query: string) => void;
}

export function AdvancedSearchDialog({ onSearch }: AdvancedSearchDialogProps) {
  const [open, setOpen] = useState(false);
  // Persisted across dialog closes and page reloads (see loadPersistedRoot/STORAGE_KEY
  // above) - a half-built query surviving an accidental close is worth more here than
  // starting fresh every time, same reasoning as an unsent draft.
  const [root, setRoot] = useState<GroupNode>(loadPersistedRoot);
  // The vocabulary is loaded the first time the dialog opens (and kept once loaded).
  const fields = useFieldOptions(open);
  // A new condition starts with the first tag category.
  const defaultField = fields[0]?.key ?? STUDY_FIELDS[0].key;

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(root));
    } catch {
      // Best-effort only - a private window or full storage shouldn't break the dialog.
    }
  }, [root]);

  const updateNode = (id: string, updater: (node: RowNode) => RowNode) =>
    setRoot((previous) => updateNodeById(previous, id, updater) as GroupNode);

  const removeNode = (id: string) => setRoot((previous) => removeNodeById(previous, id));

  const addCondition = (groupId: string) =>
    setRoot((previous) => addChildToGroup(previous, groupId, createEmptyCondition()));

  const addGroup = (groupId: string) =>
    setRoot((previous) => addChildToGroup(previous, groupId, createEmptyGroup()));

  const clearAll = () => setRoot(createEmptyGroup());

  const query = buildQuery(root, defaultField);
  const canSearch = query.trim().length > 0;

  const handleSearch = () => {
    if (!canSearch) return;
    onSearch(query);
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        // Only the icon when the search form around it is narrow (a container there).
        className="h-9 w-9 gap-1.5 has-[>svg]:px-0 @sm:w-auto @sm:has-[>svg]:px-2.5"
        aria-label="Advanced search"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <SlidersHorizontal className="h-3.5 w-3.5" />
        <span className="hidden @sm:inline">Advanced</span>
      </Button>
      <DialogContent className="flex max-h-[85vh] w-[min(92vw,640px)] max-w-[640px] flex-col gap-0 overflow-hidden rounded-2xl p-0 sm:max-w-[640px]">
        <DialogHeader className="flex-row items-center gap-3 space-y-0 px-6 pb-4 pt-6 text-left">
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary/10 text-primary">
            <SlidersHorizontal className="h-4.5 w-4.5" aria-hidden />
          </span>
          <div className="min-w-0 space-y-1">
            <DialogTitle>Advanced search</DialogTitle>
            <DialogDescription>Combine conditions on the tags and fields of a study.</DialogDescription>
          </div>
        </DialogHeader>

        {/* A container, so the rows show only the icon of their field when the dialog is narrow. */}
        <div className="@container min-h-0 flex-1 overflow-y-auto px-6 pb-5 pt-1">
          <GroupEditor
            node={root}
            isRoot
            fields={fields}
            defaultField={defaultField}
            onUpdate={updateNode}
            onRemove={removeNode}
            onAddCondition={addCondition}
            onAddGroup={addGroup}
            onSubmit={handleSearch}
          />
        </div>

        <div className="border-t bg-muted/30 px-6 py-4">
          <div className="flex items-center justify-between gap-2">
            <Button type="button" variant="ghost" size="sm" className="rounded-full" onClick={clearAll}>
              Clear all
            </Button>
            <div className="flex items-center gap-2">
              <Button type="button" variant="ghost" size="sm" className="rounded-full" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="button" className="rounded-full px-5" onClick={handleSearch} disabled={!canSearch}>
                Search
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
