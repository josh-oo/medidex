import apiClient from "./apiClient";
import { unwrap, logAndRethrow } from "./requests";
import { getAccessToken } from "@/lib/client/keycloak";
import type {
  DatabaseDto,
  DatabasePayload,
  DatabaseStatusDto,
  DatabaseStorageDto,
  DatabaseUpdate,
  EligibilitySchemaDto,
} from "../../types/apiDTOs";

export const getDatabases = (): Promise<DatabaseDto[]> =>
  apiClient.get<DatabaseDto[]>("/databases").then(unwrap).catch(logAndRethrow("Error fetching databases:"));

// The categories of the eligibility criteria of the databases, in their order.
export const getEligibilitySchema = (): Promise<EligibilitySchemaDto> =>
  apiClient
    .get<EligibilitySchemaDto>("/eligibility-schema")
    .then(unwrap)
    .catch(logAndRethrow("Error fetching the eligibility schema:"));

// A new, empty database.
export const createDatabase = (payload: DatabasePayload): Promise<DatabaseDto> =>
  apiClient.post<DatabaseDto>("/databases", payload).then(unwrap).catch(logAndRethrow("Error creating database:"));

// Renames the database or changes its description or eligibility criteria.
export const updateDatabase = (databaseId: number, update: DatabaseUpdate): Promise<DatabaseDto> =>
  apiClient
    .patch<DatabaseDto>(`/databases/${databaseId}`, update)
    .then(unwrap)
    .catch(logAndRethrow(`Error updating database ${databaseId}:`));

// A new database with the studies, reports and PDFs of an exported one (a .medidex.zip archive, or its database.json).
// Answers once the file is uploaded (`onUpload` gets how many of its bytes are), with the database to be (`importing`);
// streamDatabaseStatus follows its import.
export const importDatabase = (
  file: File,
  payload: DatabasePayload,
  onUpload?: (loaded: number, total: number) => void,
): Promise<DatabaseDto> => {
  const formData = new FormData();
  formData.append("file", file, file.name);
  formData.append("name", payload.name);
  if (payload.description) formData.append("description", payload.description);
  formData.append("eligibilityCriteria", JSON.stringify(payload.eligibilityCriteria));
  return apiClient
    .post<DatabaseDto>("/databases/import", formData, {
      onUploadProgress: (event) => onUpload?.(event.loaded, event.total ?? file.size),
    })
    .then(unwrap)
    .catch(logAndRethrow("Error importing database:"));
};

// Where a database is on its way to being usable (its import, then the indexing of its reports), as it changes: the
// first status is where it is now, the stream ends once it is ready or its import failed (`onEnd`, also if it broke
// off). Returns a function that stops the stream (without `onEnd`).
export const streamDatabaseStatus = (
  databaseId: number,
  onStatus: (status: DatabaseStatusDto) => void,
  onEnd?: () => void,
): (() => void) => {
  const abortController = new AbortController();
  const url = `${apiClient.defaults.baseURL ?? ""}/databases/${databaseId}/status`;

  const startStream = async () => {
    try {
      const headers: Record<string, string> = { Accept: "text/event-stream" };
      const token = await getAccessToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const response = await fetch(url, { headers, signal: abortController.signal });
      if (!response.ok || !response.body) {
        throw new Error(`Status stream request failed: ${response.status} ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          const data = line.startsWith("data:") ? line.slice(5).trim() : "";
          if (data) onStatus(JSON.parse(data) as DatabaseStatusDto);
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      console.error(`Error streaming the status of database ${databaseId}:`, error);
    }
    if (!abortController.signal.aborted) onEnd?.();
  };

  void startStream();
  return () => abortController.abort();
};

// The database as a zip archive (database.json and the PDFs of its reports, what importDatabase reads), to save.
export const exportDatabase = (databaseId: number): Promise<Blob> =>
  apiClient
    .get(`/databases/${databaseId}/export`, { responseType: "blob" })
    .then(unwrap)
    .catch(logAndRethrow(`Error exporting database ${databaseId}:`));

// What the database takes in storage: its data, its search index and its PDFs (admins only).
export const getDatabaseStorage = (databaseId: number): Promise<DatabaseStorageDto> =>
  apiClient
    .get<DatabaseStorageDto>(`/databases/${databaseId}/storage`)
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching the storage of database ${databaseId}:`));
