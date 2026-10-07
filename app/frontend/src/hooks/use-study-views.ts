import { useEffect, useState } from "react";
import { getStudyViews } from "@/lib/api/studiesApi";
import type { StudyViewDto } from "@/types/apiDTOs";

type Views = Record<string, StudyViewDto>;

// The views of a study (see the study schema) are fetched once per session. The requests of the studies shown
// at the same time (a list of study cards) are sent together.
const BATCH_DELAY_MS = 20;
const cache = new Map<number, Promise<Views>>();
const waiting = new Map<number, { resolve: (views: Views) => void; reject: (error: unknown) => void }>();
let timer: ReturnType<typeof setTimeout> | null = null;

const flush = () => {
  timer = null;
  const batch = new Map(waiting);
  waiting.clear();
  getStudyViews([...batch.keys()])
    .then((views) => batch.forEach(({ resolve }, id) => resolve(views[id] ?? {})))
    .catch((error) => {
      batch.forEach(({ reject }, id) => {
        cache.delete(id); // try again the next time
        reject(error);
      });
    });
};

const loadViews = (studyId: number): Promise<Views> => {
  let request = cache.get(studyId);
  if (!request) {
    request = new Promise<Views>((resolve, reject) => waiting.set(studyId, { resolve, reject }));
    cache.set(studyId, request);
    timer ??= setTimeout(flush, BATCH_DELAY_MS);
  }
  return request;
};

// The views of a study by name, or null while they load (or if they cannot be loaded).
export function useStudyViews(studyId: number): Views | null {
  const [loaded, setLoaded] = useState<{ studyId: number; views: Views } | null>(null);

  useEffect(() => {
    let active = true;
    loadViews(studyId)
      .then((views) => active && setLoaded({ studyId, views }))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [studyId]);

  return loaded?.studyId === studyId ? loaded.views : null;
}
