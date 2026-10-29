import { Fragment, type ReactNode } from "react";
import type { TagCatalog } from "@/hooks/use-tag-catalog";
import { colorClasses } from "@/lib/colors";
import type { StudyFilter } from "@/lib/study-filters";
import { FilterChip } from "./study-filter-panel";

interface QuerySummaryProps {
  /** E.g. "24 studies". */
  count: ReactNode;
  text: string;
  filters: StudyFilter[];
  allFields: string[];
  catalogs: TagCatalog[];
  onToggleAll: (field: string) => void;
  onRemove: (filter: StudyFilter) => void;
  onClearFilters: () => void;
}

/**
 * The search as a sentence above the results: "24 studies matching “diabetes” and metformin or insulin and
 * completed". The word between the values of a category is the same switch as Any / All in the filter column.
 */
export function QuerySummary({
  count,
  text,
  filters,
  allFields,
  catalogs,
  onToggleAll,
  onRemove,
  onClearFilters,
}: QuerySummaryProps) {
  // The categories in the order of the filter column, the status last.
  const order = [...catalogs.map(({ category }) => category.searchField), "status"];
  const fields = [...new Set(filters.map((filter) => filter.field))].sort((a, b) => order.indexOf(a) - order.indexOf(b));

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1.5 text-sm leading-7 text-muted-foreground">
      <span className="font-medium text-foreground">{count}</span>
      {text && <span>matching &ldquo;{text}&rdquo;</span>}
      {fields.map((field, index) => {
        const values = filters.filter((filter) => filter.field === field);
        const category = catalogs.find((catalog) => catalog.category.searchField === field)?.category;
        const colors = category ? colorClasses(category.color) : null;
        const all = allFields.includes(field);
        return (
          <Fragment key={field}>
            <span className="font-medium text-foreground">{index === 0 && !text ? "with" : "and"}</span>
            {values.map((filter, valueIndex) => (
              <Fragment key={filter.value}>
                {valueIndex > 0 && (
                  <button
                    type="button"
                    onClick={() => onToggleAll(field)}
                    title={`Switch to “${all ? "or" : "and"}”`}
                    className="border-b border-dashed border-primary/60 font-medium leading-5 text-primary hover:border-primary"
                  >
                    {all ? "and" : "or"}
                  </button>
                )}
                <FilterChip filter={filter} label={filter.value} dotClassName={colors?.accent} onRemove={onRemove} />
              </Fragment>
            ))}
          </Fragment>
        );
      })}
      {filters.length > 1 && (
        <button
          type="button"
          onClick={onClearFilters}
          className="ml-1 text-xs font-medium text-primary underline-offset-2 hover:underline"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
