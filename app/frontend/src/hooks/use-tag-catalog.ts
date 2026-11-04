import { useEffect, useState } from "react";
import apiClient from "@/lib/api/apiClient";
import { useStudySchema } from "@/hooks/use-study-schema";
import type { TagCategorySchemaDto, TagDto } from "@/types/apiDTOs";

export interface TagCatalog {
  category: TagCategorySchemaDto;
  /** The names of the tags of the category, sorted. */
  values: string[];
}

// The vocabulary of a category (GET /<category>) is loaded once per session, when it is first needed.
const cache = new Map<string, Promise<string[]>>();

const loadValues = (category: string): Promise<string[]> => {
  let request = cache.get(category);
  if (!request) {
    request = apiClient
      .get<(TagDto | string)[]>(`/${category}`)
      .then((response) =>
        Array.from(
          new Set(
            response.data
              .map((tag) => (typeof tag === "string" ? tag : tag.keyword))
              .filter((value): value is string => Boolean(value?.trim()))
          )
        ).sort((a, b) => a.localeCompare(b))
      )
      .catch((error) => {
        cache.delete(category); // try again the next time
        console.error(`Failed to load the ${category} vocabulary:`, error);
        return [];
      });
    cache.set(category, request);
  }
  return request;
};

/** The vocabulary of every tag category of the study schema; loaded once `enabled`. */
export function useTagCatalogs(enabled = true): TagCatalog[] {
  const { schema } = useStudySchema();
  const [catalogs, setCatalogs] = useState<TagCatalog[]>([]);

  useEffect(() => {
    if (!schema || !enabled) return;
    let active = true;
    Promise.all(schema.tags.map((category) => loadValues(category.key).then((values) => ({ category, values })))).then(
      (loaded) => active && setCatalogs(loaded)
    );
    return () => {
      active = false;
    };
  }, [schema, enabled]);

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
