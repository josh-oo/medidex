import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { Check, Plus, SlidersHorizontal, X } from "lucide-react";
import { getInterventions } from "@/lib/api/interventionsApi";
import { getConditions } from "@/lib/api/conditionsApi";
import { getOutcomes } from "@/lib/api/outcomesApi";
import { getParticipants } from "@/lib/api/participantsApi";
import { getDesigns } from "@/lib/api/designApi";
import { COUNTRY_OPTIONS, STUDY_STATUS_OPTIONS } from "./constants";

// Fields the backend's advanced-search grammar accepts (see the backend's
// src/utils/query_parser.py and StudyRepository.search_studies_advanced) - field names
// are matched case-insensitively there, so the labels below are just for display.
type CatalogFieldKey =
  | "intervention"
  | "condition"
  | "outcome"
  | "participant"
  | "design"
  | "country";

type FieldKey = "name" | "trialId" | "author" | "status" | CatalogFieldKey;

type FieldKind = "text" | "select" | "catalog";

interface FieldConfig {
  key: FieldKey;
  label: string;
  kind: FieldKind;
  placeholder?: string;
}

const FIELD_CONFIGS: FieldConfig[] = [
  { key: "intervention", label: "Intervention", kind: "catalog" },
  { key: "condition", label: "Condition", kind: "catalog" },
  { key: "outcome", label: "Outcome", kind: "catalog" },
  { key: "participant", label: "Participant", kind: "catalog" },
  { key: "design", label: "Design", kind: "catalog" },
  { key: "country", label: "Country", kind: "catalog" },
  { key: "name", label: "Study name", kind: "text", placeholder: "e.g. Steiner 1995" },
  { key: "trialId", label: "Trial ID", kind: "text", placeholder: "e.g. NCT01234567" },
  { key: "author", label: "Author", kind: "text", placeholder: "e.g. Smith" },
  { key: "status", label: "Status", kind: "select" },
];

const FIELD_CONFIG_BY_KEY: Record<FieldKey, FieldConfig> = Object.fromEntries(
  FIELD_CONFIGS.map((config) => [config.key, config])
) as Record<FieldKey, FieldConfig>;

type Operator = "AND" | "OR";

// A bracket-group builder: mirrors the backend's Comparison/AndGroup/OrGroup tree
// (src/utils/query_parser.py) - a group's `operator` applies to all of its direct
// `children`; mixing AND and OR at one level means nesting a sub-group, same as the
// backend's structured form. This is what gets rendered into the parenthesized string
// the REST API's advanced search takes (buildQuery below).
interface ConditionNode {
  kind: "condition";
  id: string;
  field: FieldKey;
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
  field: "intervention",
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

const dedupeSorted = (values: (string | null | undefined)[]): string[] =>
  Array.from(new Set(values.filter((value): value is string => Boolean(value?.trim())))).sort(
    (a, b) => a.localeCompare(b)
  );

const EMPTY_CATALOGS: Record<CatalogFieldKey, string[]> = {
  intervention: [],
  condition: [],
  outcome: [],
  participant: [],
  design: [],
  country: COUNTRY_OPTIONS,
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
const renderNode = (node: RowNode, isRoot: boolean): string | null => {
  if (node.kind === "condition") {
    const trimmed = node.value.trim();
    if (!trimmed) return null;
    return `${node.field}==${quoteValue(trimmed)}`;
  }

  const parts = node.children
    .map((child) => renderNode(child, false))
    .filter((part): part is string => part !== null);

  if (parts.length === 0) return null;
  if (parts.length === 1) return parts[0];

  const joined = parts.join(` ${node.operator} `);
  return isRoot ? joined : `(${joined})`;
};

const buildQuery = (root: GroupNode): string => renderNode(root, true) ?? "";

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

interface CatalogValueComboboxProps {
  value: string;
  onChange: (value: string) => void;
  options: string[];
  loading?: boolean;
  placeholder: string;
}

function CatalogValueCombobox({
  value,
  onChange,
  options,
  loading,
  placeholder,
}: CatalogValueComboboxProps) {
  const [open, setOpen] = useState(false);
  const normalizedQuery = value.trim().toLowerCase();
  const matches = (
    normalizedQuery
      ? options.filter((option) => option.toLowerCase().includes(normalizedQuery))
      : options
  ).slice(0, 50);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="w-full justify-between font-normal"
        >
          <span className={`truncate text-left ${value ? "" : "text-muted-foreground"}`}>
            {value || placeholder}
          </span>
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-[min(360px,calc(100vw-3rem))] p-0"
        sideOffset={6}
      >
        <Command>
          <CommandInput value={value} onValueChange={onChange} placeholder={placeholder} />
          <CommandList className="max-h-[240px] overflow-y-auto overscroll-contain">
            {loading ? (
              <CommandEmpty className="py-4 text-muted-foreground">Loading...</CommandEmpty>
            ) : matches.length > 0 ? (
              <CommandGroup>
                {matches.map((option) => (
                  <CommandItem
                    key={option}
                    value={option}
                    onSelect={() => {
                      onChange(option);
                      setOpen(false);
                    }}
                  >
                    <span className="flex-1 truncate">{option}</span>
                    {value.toLowerCase() === option.toLowerCase() && (
                      <Check className="h-4 w-4 text-primary" />
                    )}
                  </CommandItem>
                ))}
              </CommandGroup>
            ) : (
              <CommandEmpty className="py-4 text-muted-foreground">
                No catalog match - your typed text will still be used.
              </CommandEmpty>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

interface ConditionEditorProps {
  node: ConditionNode;
  catalogs: Record<CatalogFieldKey, string[]>;
  catalogsLoading: boolean;
  onFieldChange: (field: FieldKey) => void;
  onValueChange: (value: string) => void;
  onRemove: () => void;
}

function ConditionEditor({
  node,
  catalogs,
  catalogsLoading,
  onFieldChange,
  onValueChange,
  onRemove,
}: ConditionEditorProps) {
  const config = FIELD_CONFIG_BY_KEY[node.field];

  return (
    <div className="flex items-start gap-2">
      <Select value={node.field} onValueChange={(value) => onFieldChange(value as FieldKey)}>
        <SelectTrigger className="w-[150px] shrink-0">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {FIELD_CONFIGS.map((fieldConfig) => (
            <SelectItem key={fieldConfig.key} value={fieldConfig.key}>
              {fieldConfig.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="flex-1">
        {config.kind === "text" && (
          <Input
            value={node.value}
            placeholder={config.placeholder}
            onChange={(event) => onValueChange(event.target.value)}
          />
        )}
        {config.kind === "select" && (
          <Select value={node.value} onValueChange={onValueChange}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Choose status" />
            </SelectTrigger>
            <SelectContent>
              {STUDY_STATUS_OPTIONS.map((status) => (
                <SelectItem key={status} value={status}>
                  {status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {config.kind === "catalog" && (
          <CatalogValueCombobox
            value={node.value}
            onChange={onValueChange}
            options={catalogs[node.field as CatalogFieldKey]}
            loading={catalogsLoading}
            placeholder={`Search ${config.label.toLowerCase()}...`}
          />
        )}
      </div>

      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={onRemove}
        aria-label="Remove condition"
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

interface GroupEditorProps {
  node: GroupNode;
  isRoot: boolean;
  catalogs: Record<CatalogFieldKey, string[]>;
  catalogsLoading: boolean;
  onUpdate: (id: string, updater: (node: RowNode) => RowNode) => void;
  onRemove: (id: string) => void;
  onAddCondition: (groupId: string) => void;
  onAddGroup: (groupId: string) => void;
}

function GroupEditor({
  node,
  isRoot,
  catalogs,
  catalogsLoading,
  onUpdate,
  onRemove,
  onAddCondition,
  onAddGroup,
}: GroupEditorProps) {
  return (
    <div
      className={
        isRoot
          ? "space-y-3"
          : "space-y-3 rounded-lg border border-border bg-muted/20 p-3 border-l-2 border-l-primary/40"
      }
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
          <span>Match</span>
          <Select
            value={node.operator}
            onValueChange={(value) => onUpdate(node.id, (current) => ({ ...current, operator: value as Operator }))}
          >
            <SelectTrigger className="w-20 h-7 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="AND">ALL</SelectItem>
              <SelectItem value="OR">ANY</SelectItem>
            </SelectContent>
          </Select>
          <span>of the following:</span>
        </div>
        {!isRoot && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onRemove(node.id)}
            aria-label="Remove group"
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      <div className="space-y-2">
        {node.children.map((child) =>
          child.kind === "condition" ? (
            <ConditionEditor
              key={child.id}
              node={child}
              catalogs={catalogs}
              catalogsLoading={catalogsLoading}
              onFieldChange={(field) => onUpdate(child.id, (current) => ({ ...current, field, value: "" }))}
              onValueChange={(value) => onUpdate(child.id, (current) => ({ ...current, value }))}
              onRemove={() => onRemove(child.id)}
            />
          ) : (
            <GroupEditor
              key={child.id}
              node={child}
              isRoot={false}
              catalogs={catalogs}
              catalogsLoading={catalogsLoading}
              onUpdate={onUpdate}
              onRemove={onRemove}
              onAddCondition={onAddCondition}
              onAddGroup={onAddGroup}
            />
          )
        )}
      </div>

      <div className="flex items-center gap-1">
        <Button type="button" variant="ghost" size="sm" className="gap-1.5" onClick={() => onAddCondition(node.id)}>
          <Plus className="h-4 w-4" />
          Add condition
        </Button>
        <Button type="button" variant="ghost" size="sm" className="gap-1.5" onClick={() => onAddGroup(node.id)}>
          <Plus className="h-4 w-4" />
          Add group (...)
        </Button>
      </div>
    </div>
  );
}

interface AdvancedSearchDialogProps {
  onSearch: (query: string) => void;
}

export function AdvancedSearchDialog({ onSearch }: AdvancedSearchDialogProps) {
  const [open, setOpen] = useState(false);
  // Persisted across dialog closes and page reloads (see loadPersistedRoot/STORAGE_KEY
  // below) - a half-built query surviving an accidental close is worth more here than
  // starting fresh every time, same reasoning as an unsent draft.
  const [root, setRoot] = useState<GroupNode>(loadPersistedRoot);
  const [catalogs, setCatalogs] = useState<Record<CatalogFieldKey, string[]>>(EMPTY_CATALOGS);
  const [catalogsLoading, setCatalogsLoading] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(root));
    } catch {
      // Best-effort only - a private window or full storage shouldn't break the dialog.
    }
  }, [root]);

  useEffect(() => {
    if (!open) return;

    const controller = new AbortController();
    setCatalogsLoading(true);

    Promise.all([
      getInterventions({ signal: controller.signal }).catch(() => []),
      getConditions({ signal: controller.signal }).catch(() => []),
      getOutcomes({ signal: controller.signal }).catch(() => []),
      getParticipants({ signal: controller.signal }).catch(() => []),
      getDesigns({ signal: controller.signal }).catch(() => []),
    ])
      .then(([interventions, conditions, outcomes, participants, designs]) => {
        if (controller.signal.aborted) return;
        setCatalogs({
          intervention: dedupeSorted(interventions.map((tag) => tag.keyword)),
          condition: dedupeSorted(conditions.map((tag) => tag.keyword)),
          outcome: dedupeSorted(outcomes.map((tag) => tag.keyword)),
          participant: dedupeSorted(participants.map((participant) => participant.description)),
          design: dedupeSorted(designs.map((design) => design.description)),
          country: COUNTRY_OPTIONS,
        });
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setCatalogsLoading(false);
        }
      });

    return () => controller.abort();
  }, [open]);

  const updateNode = (id: string, updater: (node: RowNode) => RowNode) =>
    setRoot((previous) => updateNodeById(previous, id, updater) as GroupNode);

  const removeNode = (id: string) => setRoot((previous) => removeNodeById(previous, id));

  const addCondition = (groupId: string) =>
    setRoot((previous) => addChildToGroup(previous, groupId, createEmptyCondition()));

  const addGroup = (groupId: string) =>
    setRoot((previous) => addChildToGroup(previous, groupId, createEmptyGroup()));

  const clearAll = () => setRoot(createEmptyGroup());

  const previewQuery = buildQuery(root);
  const canSearch = previewQuery.trim().length > 0;

  const handleSearch = () => {
    if (!canSearch) return;
    onSearch(previewQuery);
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-9 gap-1.5"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <SlidersHorizontal className="h-3.5 w-3.5" />
        Advanced
      </Button>
      <DialogContent className="max-w-[640px] w-[min(92vw,640px)] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Advanced search</DialogTitle>
          <DialogDescription>
            Combine field conditions with AND / OR.
          </DialogDescription>
        </DialogHeader>

        <GroupEditor
          node={root}
          isRoot
          catalogs={catalogs}
          catalogsLoading={catalogsLoading}
          onUpdate={updateNode}
          onRemove={removeNode}
          onAddCondition={addCondition}
          onAddGroup={addGroup}
        />

        <DialogFooter className="sm:justify-between">
          <Button type="button" variant="ghost" onClick={clearAll}>
            Clear all
          </Button>
          <div className="flex items-center gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={handleSearch} disabled={!canSearch}>
              Search
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
