import apiClient from "./apiClient";
import { unwrap, logAndRethrow } from "./requests";
import type { DatabaseDto, DatabasePayload, DatabaseStorageDto, DatabaseUpdate } from "../../types/apiDTOs";

export const getDatabases = (): Promise<DatabaseDto[]> =>
  apiClient.get<DatabaseDto[]>("/databases").then(unwrap).catch(logAndRethrow("Error fetching databases:"));

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
export const importDatabase = (file: File, payload: DatabasePayload): Promise<DatabaseDto> => {
  const formData = new FormData();
  formData.append("file", file, file.name);
  formData.append("name", payload.name);
  if (payload.description) formData.append("description", payload.description);
  formData.append("eligibilityCriteria", payload.eligibilityCriteria);
  return apiClient
    .post<DatabaseDto>("/databases/import", formData)
    .then(unwrap)
    .catch(logAndRethrow("Error importing database:"));
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
