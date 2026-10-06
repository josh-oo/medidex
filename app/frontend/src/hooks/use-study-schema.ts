import { useEffect, useState } from "react";
import { getStudySchema } from "@/lib/api/studiesApi";
import type { StudySchemaDto } from "@/types/apiDTOs";

// The study schema is the same for every study and for the whole session, so it is fetched once.
let schemaRequest: Promise<StudySchemaDto> | null = null;

const loadStudySchema = (): Promise<StudySchemaDto> => {
  if (!schemaRequest) {
    schemaRequest = getStudySchema().catch((error) => {
      schemaRequest = null; // try again the next time it is needed
      throw error;
    });
  }
  return schemaRequest;
};

export function useStudySchema(): { schema: StudySchemaDto | null; error: string | null } {
  const [schema, setSchema] = useState<StudySchemaDto | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    loadStudySchema()
      .then((loaded) => active && setSchema(loaded))
      .catch((failure) =>
        active && setError(failure instanceof Error ? failure.message : "Unable to load the study schema")
      );
    return () => {
      active = false;
    };
  }, []);

  return { schema, error };
}

// The allowed values of an enum field of the study schema (empty until the schema is loaded).
export function useStudyFieldValues(field: string): string[] {
  const { schema } = useStudySchema();
  return schema?.fields.find((candidate) => candidate.key === field)?.values ?? [];
}
