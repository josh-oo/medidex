// The study databases: separate collections of studies, each with its own projects that bring new reports to it. The
// list is loaded once and shared by every view (the search picker, the database management); refreshStudyDatabases()
// loads it again after a change.
import { useEffect, useSyncExternalStore } from "react";
import { getDatabases } from "@/lib/api/databaseApi";
import type { DatabaseDto } from "@/types/apiDTOs";

export interface StudyDatabase {
  id: number;
  name: string;
  description?: string;
  eligibilityCriteria: string;
  numberStudies: number;
  numberReports: number;
  /** Its reports are still being added to the vectorstore (see DatabaseDto.indexing). */
  indexing: boolean;
  numberReportsIndexed: number;
}

interface DatabaseState {
  loaded: boolean;
  /** The last load failed (the databases may still be those of an earlier one). */
  failed: boolean;
  databases: StudyDatabase[];
}

let state: DatabaseState = { loaded: false, failed: false, databases: [] };
let pending: Promise<void> | null = null;
const listeners = new Set<() => void>();

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  scheduleRefresh();
  return () => listeners.delete(listener);
};

const toStudyDatabase = (dto: DatabaseDto): StudyDatabase => ({
  id: dto.databaseId,
  name: dto.name,
  description: dto.description || undefined,
  eligibilityCriteria: dto.eligibilityCriteria,
  numberStudies: dto.numberStudies,
  numberReports: dto.numberReports,
  indexing: dto.indexing,
  numberReportsIndexed: dto.numberReportsIndexed,
});

// While a database is being indexed, the list is loaded again every few seconds, as long as a view shows it.
const INDEXING_REFRESH_MS = 5000;
let refreshTimer: ReturnType<typeof setTimeout> | null = null;

const scheduleRefresh = () => {
  if (refreshTimer !== null || listeners.size === 0 || !state.databases.some((database) => database.indexing)) return;
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    void refreshStudyDatabases();
  }, INDEXING_REFRESH_MS);
};

/** Loads the databases (again), e.g. after one was created; the views using them update. */
export function refreshStudyDatabases(): Promise<void> {
  pending ??= getDatabases()
    .then((dtos) => {
      state = { loaded: true, failed: false, databases: dtos.map(toStudyDatabase) };
    })
    .catch(() => {
      state = { ...state, loaded: true, failed: true };
    })
    .finally(() => {
      pending = null;
      listeners.forEach((listener) => listener());
      scheduleRefresh();
    });
  return pending;
}

/** The databases, the oldest first; loads them the first time they are asked for. There may be none yet. */
export function useStudyDatabases(): DatabaseState {
  const current = useSyncExternalStore(subscribe, () => state);
  useEffect(() => {
    if (!state.loaded) void refreshStudyDatabases();
  }, []);
  return current;
}

/** The ids of databases kept in the URL (?db=1&db=2), without what is no id. */
export function parseDatabaseIds(values: string[]): number[] {
  return values.map(Number).filter((id) => Number.isInteger(id) && id > 0);
}

/** The database a project adds its reports to. */
export function projectDatabaseId(project: { databaseId: number }): number {
  return project.databaseId;
}
