import { useEffect, useState } from "react";
import { getEligibilitySchema } from "@/lib/api/databaseApi";
import type { EligibilityCategoryDto, EligibilitySchemaDto } from "@/types/apiDTOs";

// The categories of the eligibility criteria are the same for the whole session, so they are fetched once.
let schemaRequest: Promise<EligibilitySchemaDto> | null = null;

const loadEligibilitySchema = (): Promise<EligibilitySchemaDto> => {
  if (!schemaRequest) {
    schemaRequest = getEligibilitySchema().catch((error) => {
      schemaRequest = null; // try again the next time it is needed
      throw error;
    });
  }
  return schemaRequest;
};

/** The categories of the eligibility criteria, in their order (empty until they are loaded). */
export function useEligibilityCategories(): EligibilityCategoryDto[] {
  const [categories, setCategories] = useState<EligibilityCategoryDto[]>([]);

  useEffect(() => {
    let active = true;
    loadEligibilitySchema()
      .then((schema) => active && setCategories(schema.categories))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  return categories;
}
