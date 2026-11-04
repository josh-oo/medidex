import { useEffect, useState } from "react";
import apiClient from "@/lib/api/apiClient";
import { useStudySchema } from "@/hooks/use-study-schema";
import type { TagCategorySchemaDto, TagDto } from "@/types/apiDTOs";

const NO_DATABASES: number[] = [];

export interface TagCatalog {
  category: TagCategorySchemaDto;
  /** The names of the tags of the category, sorted. */
  values: string[];
}

// The vocabulary of a category (GET /<category>) per choice of databases, loaded when it is needed. Tags change while
// the app is open (an imported database, a new study), so a loaded vocabulary is only reused for a while: enough for
// the views of one page to share a request.
const FRESH_MS = 60_000;
const cache = new Map<string, Promise<string[]>>();

const loadValues = (category: string, databases: number[]): Promise<string[]> => {
  const key = [category, ...databases].join("\n");
  let request = cache.get(key);
  if (!request) {
    request = apiClient
      .get<(TagDto | string)[]>(`/${category}`, { params: { databases } })
      .then((response) =>
        Array.from(
          new Set(
            response.data
              .map((tag) => (typeof tag === "string" ? tag : tag.keyword))
              .filter((value): value is string => Boolean(value?.trim()))
          )
        ).sort((a, b) => a.localeCompare(b))
      )
      .finally(() => setTimeout(() => cache.get(key) === request && cache.delete(key), FRESH_MS))
      .catch((error) => {
        cache.delete(key); // try again the next time
        console.error(`Failed to load the ${category} vocabulary:`, error);
        return [];
      });
    cache.set(key, request);
  }
  return request;
};

/**
 * The vocabulary of every tag category of the study schema; loaded once `enabled`. With `databases`, only the tags of
 * the studies of those databases (all of them if empty).
 */
export function useTagCatalogs(enabled = true, databases: number[] = NO_DATABASES): TagCatalog[] {
  const { schema } = useStudySchema();
  const [catalogs, setCatalogs] = useState<TagCatalog[]>([]);

  useEffect(() => {
    if (!schema || !enabled) return;
    let active = true;
    Promise.all(
      schema.tags.map((category) => loadValues(category.key, databases).then((values) => ({ category, values })))
    ).then((loaded) => active && setCatalogs(loaded));
    return () => {
      active = false;
    };
  }, [schema, enabled, databases]);

  return catalogs;
}

/** Values of a catalog that contain `text`, the ones starting with it first. */
export const matchValues = (values: string[], text: string, limit: number): string[] => {
  const needle = text.trim().toLowerCase();
  if (!needle) return values.slice(0, limit);
  const starts: string[] = [];
  const contains: string[] = [];
  for (const value of values) {
    const lower = value.toLowerCase();
    if (lower.startsWith(needle)) starts.push(value);
    else if (lower.includes(needle)) contains.push(value);
    if (starts.length >= limit) break;
  }
  return [...starts, ...contains].slice(0, limit);
};
