import { Upload } from "tus-js-client";
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

// The parts an upload is sent in stay below what a proxy in front of the backend lets through in one request (a
// Cloudflare tunnel: 100 MB).
const UPLOAD_PART_BYTES = 64 * 1024 * 1024;

// Uploads a file with tus (POST /databases/uploads) and resolves to the id of the upload. A part that failed is sent
// again; an upload of the same file that broke off (e.g. the page was loaded again) goes on where it stopped.
const uploadFile = (file: File, onUpload?: (loaded: number, total: number) => void): Promise<string> =>
  new Promise((resolve, reject) => {
    const upload = new Upload(file, {
      endpoint: `${apiClient.defaults.baseURL ?? ""}/databases/uploads`,
      chunkSize: UPLOAD_PART_BYTES,
      retryDelays: [0, 3000, 10000, 30000, 60000],
      metadata: { filename: file.name },
      removeFingerprintOnSuccess: true,
      // A new token for every part: a proxy may only pass a part on once all of it arrived, and the token has to be
      // valid still then.
      onBeforeRequest: async (request) => {
        const token = await getAccessToken(true);
        if (token) request.setHeader("Authorization", `Bearer ${token}`);
      },
      // tus-js-client's own rule (no answer, a server error, a conflict or a lock), and an expired token too: a part
      // that took longer than the token lived is sent again with a new one.
      onShouldRetry: (error) => {
        const status = error.originalResponse?.getStatus() ?? 0;
        return status === 0 || status >= 500 || [401, 409, 423].includes(status);
      },
      onProgress: (loaded, total) => onUpload?.(loaded, total),
      onSuccess: () => resolve(upload.url?.split("/").pop() ?? ""),
      onError: reject,
    });
    upload.findPreviousUploads().then((previous) => {
      if (previous.length > 0) upload.resumeFromPreviousUpload(previous[0]);
      upload.start();
    }, reject);
  });

// A new database with the studies, reports and PDFs of an exported one (a .medidex.zip archive, or its database.json).
// The file is uploaded first (`onUpload` gets how many of its bytes are), then it answers with the database to be
// (`importing`); streamDatabaseStatus follows its import.
export const importDatabase = async (
  file: File,
  payload: DatabasePayload,
  onUpload?: (loaded: number, total: number) => void,
): Promise<DatabaseDto> => {
  try {
    const uploadId = await uploadFile(file, onUpload);
    return unwrap(await apiClient.post<DatabaseDto>("/databases/import", { ...payload, uploadId }));
  } catch (error) {
    return logAndRethrow("Error importing database:")(error);
  }
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
