import { useEffect, useState } from "react";
import { getStudyGraphs } from "@/lib/api/studiesApi";
import type { StudyGraphDto } from "@/types/apiDTOs";

// The graph of a study (see the study schema) is fetched once per session. The requests of the studies shown
// at the same time (a list of study cards) are sent together.
const BATCH_DELAY_MS = 20;
const EMPTY: StudyGraphDto = { nodes: [], edges: [], text: null };
const cache = new Map<number, Promise<StudyGraphDto>>();
const waiting = new Map<number, { resolve: (graph: StudyGraphDto) => void; reject: (error: unknown) => void }>();
let timer: ReturnType<typeof setTimeout> | null = null;

const flush = () => {
  timer = null;
  const batch = new Map(waiting);
  waiting.clear();
  getStudyGraphs([...batch.keys()])
    .then((graphs) => batch.forEach(({ resolve }, id) => resolve(graphs[id] ?? EMPTY)))
    .catch((error) => {
      batch.forEach(({ reject }, id) => {
        cache.delete(id); // try again the next time
        reject(error);
      });
    });
};

const loadGraph = (studyId: number): Promise<StudyGraphDto> => {
  let request = cache.get(studyId);
  if (!request) {
    request = new Promise<StudyGraphDto>((resolve, reject) => waiting.set(studyId, { resolve, reject }));
    cache.set(studyId, request);
    timer ??= setTimeout(flush, BATCH_DELAY_MS);
  }
  return request;
};

// The graph of a study, or null while it loads (or if it cannot be loaded).
export function useStudyGraph(studyId: number): StudyGraphDto | null {
  const [loaded, setLoaded] = useState<{ studyId: number; graph: StudyGraphDto } | null>(null);

  useEffect(() => {
    let active = true;
    loadGraph(studyId)
      .then((graph) => active && setLoaded({ studyId, graph }))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [studyId]);

  return loaded?.studyId === studyId ? loaded.graph : null;
}
