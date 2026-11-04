// The study search of the start page: a free text and filters (a field of the advanced search grammar and a value,
// see the backend's src/utils/query_parser.py), turned into one query. The values of a field are alternatives (OR)
// unless the field is set to match all of them (AND); different fields must all match.

import type { TagCategorySchemaDto } from "@/types/apiDTOs";

export interface StudyFilter {
  /** A field of the grammar: the search field of a tag category (e.g. "intervention") or "status". */
  field: string;
  value: string;
}

// The study's own fields the plain free-text search looks in (GET /studies?q=); the tag categories with freeTextSearch
// are added (the backend reads the same flag). With filters the text becomes comparisons of these fields.
const FREE_TEXT_COLUMNS = ["name", "trialId", "author"];

export const freeTextFields = (categories: TagCategorySchemaDto[]): string[] => [
  ...FREE_TEXT_COLUMNS,
  ...categories.filter((category) => category.freeTextSearch).map((category) => category.searchField),
];

// The grammar has no escapes: quote with the quote character the value does not contain.
const quote = (value: string) => (value.includes('"') ? `'${value}'` : `"${value}"`);

const anyOf = (comparisons: string[]) =>
  comparisons.length === 1 ? comparisons[0] : `(${comparisons.join(" OR ")})`;

/** `textFields`: where the text is looked for (see freeTextFields); `allFields`: the fields whose values must all match
 * instead of any of them. */
export function buildStudyQuery(
  text: string,
  filters: StudyFilter[],
  textFields: string[],
  allFields: string[] = []
): string {
  const trimmed = text.trim();
  if (filters.length === 0) return trimmed;

  const parts: string[] = [];
  if (trimmed) parts.push(anyOf(textFields.map((field) => `${field}==${quote(trimmed)}`)));
  const byField = new Map<string, string[]>();
  filters.forEach(({ field, value }) => byField.set(field, [...(byField.get(field) ?? []), value]));
  byField.forEach((values, field) => {
    const comparisons = values.map((value) => `${field}==${quote(value)}`);
    // At the top level AND needs no parentheses.
    if (allFields.includes(field)) parts.push(...comparisons);
    else parts.push(anyOf(comparisons));
  });
  return parts.join(" AND ");
}

export const sameFilter = (a: StudyFilter, b: StudyFilter) =>
  a.field === b.field && a.value.toLowerCase() === b.value.toLowerCase();

// In the URL a filter is `f=field:value`.
export const filterToParam = ({ field, value }: StudyFilter) => `${field}:${value}`;

export const filterFromParam = (param: string): StudyFilter | null => {
  const separator = param.indexOf(":");
  if (separator <= 0 || separator === param.length - 1) return null;
  return { field: param.slice(0, separator), value: param.slice(separator + 1) };
};
