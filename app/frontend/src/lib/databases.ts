// The study databases: separate collections of studies, each with its own projects that bring new reports to it. The
// list is loaded once and shared by every view (the search picker, the database management); refreshStudyDatabases()
// loads it again after a change. The import and indexing of a database are followed by its status stream.
import { useEffect, useSyncExternalStore } from "react";
import axios from "axios";
import { toast } from "sonner";
import { getDatabases, importDatabase, streamDatabaseStatus } from "@/lib/api/databaseApi";
import type { DatabaseDto, DatabasePayload, DatabaseStatusDto, EligibilityCriterion } from "@/types/apiDTOs";

export interface StudyDatabase {
  id: number;
  name: string;
  description?: string;
  eligibilityCriteria: EligibilityCriterion[];
  numberStudies: number;
  numberReports: number;
  /** Its reports are still being added to the vectorstore (see DatabaseDto.indexing). */
  indexing: boolean;
  numberReportsIndexed: number;
  /** Why its indexing stopped (see DatabaseDto.indexingError). */
  indexingError?: string;
  /** It is still being imported (see DatabaseDto.importing). */
  importing: boolean;
  /** How far its import or indexing is, as its status stream last said; none before it said anything. */
  status?: DatabaseStatusDto;
}

/** The file of an import (startDatabaseImport) while it is uploaded: its database has no id before it is. */
export interface DatabaseUpload {
  key: number;
  name: string;
  loaded: number;
  total: number;
}

interface DatabaseState {
  loaded: boolean;
  /** The last load failed (the databases may still be those of an earlier one). */
  failed: boolean;
  databases: StudyDatabase[];
  /** The imports of this page whose file is still being uploaded. */
  uploads: DatabaseUpload[];
}

let state: DatabaseState = { loaded: false, failed: false, databases: [], uploads: [] };
let pending: Promise<void> | null = null;
const listeners = new Set<() => void>();

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  syncStreams();
  return () => {
    listeners.delete(listener);
    syncStreams();
  };
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
  indexingError: dto.indexingError || undefined,
  importing: dto.importing,
});

// The status stream of every database that is being imported or indexed, as long as a view shows the databases (not
// of one whose indexing failed: it is tried again only on the next start of the backend). A stream that broke off is
// started again after a while, by loading the list again.
const RECONNECT_MS = 5000;
const streams = new Map<number, () => void>();
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

const notify = () => listeners.forEach((listener) => listener());

const syncStreams = () => {
  const wanted = new Set(
    listeners.size === 0
      ? []
      : state.databases
          .filter((database) => database.importing || (database.indexing && !database.indexingError))
          .map((database) => database.id),
  );
  streams.forEach((stop, databaseId) => {
    if (wanted.has(databaseId)) return;
    stop();
    streams.delete(databaseId);
  });
  wanted.forEach((databaseId) => {
    if (streams.has(databaseId)) return;
    let ended = false;
    const stop = streamDatabaseStatus(
      databaseId,
      (status) => {
        if (status.stage === "ready" || status.stage === "failed") ended = true;
        onStatus(status);
      },
      () => {
        streams.delete(databaseId);
        if (!ended && reconnectTimer === null) {
          reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            void refreshStudyDatabases();
          }, RECONNECT_MS);
        }
      },
    );
    streams.set(databaseId, stop);
  });
};

// A status of a database: its numbers change with it; once it is ready, or its import or indexing failed, the list is
// loaded again (a database whose import failed is no longer in it, one whose indexing failed says why).
const onStatus = (status: DatabaseStatusDto) => {
  const database = state.databases.find((candidate) => candidate.id === status.databaseId);
  if (status.stage === "failed") {
    const step = database && !database.importing ? "indexing" : "import";
    toast.error(`The ${step} of "${database?.name ?? `database ${status.databaseId}`}" failed`, {
      description: status.message ?? undefined,
    });
  }
  if (status.stage === "ready" || status.stage === "failed") {
    void refreshStudyDatabases();
    return;
  }
  // Imported: its numbers of studies and reports are known now.
  if (database?.importing && status.stage === "indexing") void refreshStudyDatabases();
  state = {
    ...state,
    databases: state.databases.map((candidate) =>
      candidate.id !== status.databaseId
        ? candidate
        : {
            ...candidate,
            status,
            importing: status.stage === "importing",
            indexing: candidate.indexing || status.stage === "indexing",
            numberReportsIndexed: status.stage === "indexing" ? status.done : candidate.numberReportsIndexed,
            numberReports: status.stage === "indexing" ? Math.max(status.total, candidate.numberReports) : candidate.numberReports,
          },
    ),
  };
  notify();
};

/** Loads the databases (again), e.g. after one was created; the views using them update. */
export function refreshStudyDatabases(): Promise<void> {
  pending ??= getDatabases()
    .then((dtos) => {
      // What the stream of a database still being imported or indexed said is kept until it says more.
      const statuses = new Map(state.databases.map((database) => [database.id, database.status]));
      const databases = dtos.map(toStudyDatabase).map((database) =>
        database.importing || database.indexing ? { ...database, status: statuses.get(database.id) } : database,
      );
      state = { ...state, loaded: true, failed: false, databases };
    })
    .catch(() => {
      state = { ...state, loaded: true, failed: true };
    })
    .finally(() => {
      pending = null;
      notify();
      syncStreams();
    });
  return pending;
}

let uploadKey = 0;

// Leaving the page would end an upload.
const warnOnLeave = (event: BeforeUnloadEvent) => event.preventDefault();

const setUploads = (uploads: DatabaseUpload[]) => {
  if (uploads.length > 0 && state.uploads.length === 0) window.addEventListener("beforeunload", warnOnLeave);
  if (uploads.length === 0 && state.uploads.length > 0) window.removeEventListener("beforeunload", warnOnLeave);
  state = { ...state, uploads };
  notify();
};

/**
 * Imports an exported database (importDatabase): its file is listed as an upload (`uploads`) while it is uploaded,
 * then the database as being imported. A rejected file is shown as an error.
 */
export async function startDatabaseImport(file: File, payload: DatabasePayload): Promise<void> {
  const key = ++uploadKey;
  setUploads([...state.uploads, { key, name: payload.name, loaded: 0, total: file.size }]);
  try {
    await importDatabase(file, payload, (loaded, total) =>
      setUploads(state.uploads.map((upload) => (upload.key === key ? { ...upload, loaded, total } : upload))),
    );
    await refreshStudyDatabases();
  } catch (error) {
    const detail = axios.isAxiosError(error) ? error.response?.data?.detail : undefined;
    toast.error(`The import of "${payload.name}" failed`, {
      description: typeof detail === "string" ? detail : "The file could not be uploaded.",
    });
  } finally {
    setUploads(state.uploads.filter((upload) => upload.key !== key));
  }
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
