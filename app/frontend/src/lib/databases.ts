// The study databases a search can cover. There is only one for now and the backend has neither a selection nor
// more databases yet: the picker of the search bar keeps the choice in the URL (?db=) for when it does, and a
// database "created" there only lives in this session (a mock of the feature).
import { useSyncExternalStore } from "react";

export interface StudyDatabase {
  id: string;
  name: string;
  description?: string;
}

/** The database there is today, which every project belongs to until projects carry a database of their own. */
export const DEFAULT_DATABASE_ID = "medidex";

let databases: StudyDatabase[] = [{ id: DEFAULT_DATABASE_ID, name: "Medidex" }];
const listeners = new Set<() => void>();

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export function useStudyDatabases(): StudyDatabase[] {
  return useSyncExternalStore(subscribe, () => databases);
}

/** Mock: adds a database for this session only. */
export function addStudyDatabase(name: string, description?: string): StudyDatabase {
  const base = name.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "database";
  let id = base;
  for (let n = 2; databases.some((database) => database.id === id); n++) id = `${base}-${n}`;
  const database = { id, name: name.trim(), description: description?.trim() || undefined };
  databases = [...databases, database];
  listeners.forEach((listener) => listener());
  return database;
}

/** The database a project adds its reports to. Projects do not say yet, so it is the one database there is. */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function projectDatabaseId(_project: { projectId: string }): string {
  return DEFAULT_DATABASE_ID;
}
