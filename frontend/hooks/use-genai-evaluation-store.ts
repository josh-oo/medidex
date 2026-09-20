"use client";

import { create } from "zustand";
// import { evaluateStudiesStream } from "@/lib/api/genaiStreamApi";
import type { PromptOverrides, ReportDto, StreamEvent, StudyDto} from "@/types/apiDTOs";
export type { PromptOverrides, DefaultPrompts } from "@/types/apiDTOs";

export type AIClassification = "match" | "likely_match" | "unsure" | "not_match" | "very_likely";
export type AIModel = "gpt-5.2" | "gpt-5" | "gpt-5-mini" | "gpt-4.1";

export interface StudyAIResult {
  studyId: number;
  classification: AIClassification;
  reason: string;
}

interface ReportEvaluationState {
  isStreaming: boolean;
  streamMessages: StreamEvent[];
  currentMessage: string | null;
  processedStudies: number;
  totalStudies: number;
  error: string | null;
}

// Using plain objects instead of Maps for better Zustand reactivity
type ResultsMap = Record<string, Record<number, StudyAIResult>>;
type EvaluationsMap = Record<string, ReportEvaluationState>;

interface GenAIEvaluationStore {
  results: ResultsMap;
  evaluationsByReport: EvaluationsMap;
  runningEvaluations: number[];
  streamCleanups: Record<string, () => void>;
  dismissedSuggestions: Set<string>;

  canStartEvaluation: () => boolean;
  isSuggestionDismissed: (suggestionKey: string) => boolean;
  dismissSuggestion: (suggestionKey: string) => void;
  getReportEvaluationState: (reportId: number) => ReportEvaluationState | null;
  isEvaluationRunning: (reportId: number) => boolean;
  getRunningEvaluationsCount: () => number;
  getStudyResult: ( reportId: number, studyId: number) => StudyAIResult | null;
  getResultsForReport: ( reportId: number) => Record<number, StudyAIResult> | undefined;
  
  addStudyResult: (reportId: number, studyId: number, classification: AIClassification, reason: string) => void;
  updateClassification: (reportId: number, studyId: number, classification: AIClassification, reason?: string) => void;
  setEvaluationState: (reportId: number, state: Partial<ReportEvaluationState>) => void;
  startEvaluation: (reportId: number, totalStudies: number) => void;
  endEvaluation: (reportId: number, error?: string) => void;
  
  evaluateStream: (
    report: ReportDto,
    studies: StudyDto[],
    options: { model?: AIModel; includePdf?: boolean; promptOverrides?: PromptOverrides },
    onStreamComplete?: () => void
  ) => () => void;
  
  cancelStream: (projectId?: string, reportId?: number) => void;
  clearResults: (projectId?: string, reportId?: number) => void;
}

export const useGenAIEvaluationStore = create<GenAIEvaluationStore>((set, get) => ({
  results: {},
  evaluationsByReport: {},
  runningEvaluations: [],
  streamCleanups: {},
  dismissedSuggestions: new Set(),

  canStartEvaluation: () => get().runningEvaluations.length < 4,

  isSuggestionDismissed: (suggestionKey: string) => get().dismissedSuggestions.has(suggestionKey),

  dismissSuggestion: (suggestionKey: string) => {
    set((state) => {
      const newSet = new Set(state.dismissedSuggestions);
      newSet.add(suggestionKey);
      return { dismissedSuggestions: newSet };
    });
  },

  getReportEvaluationState: (reportId: number) => {
    return get().evaluationsByReport[reportId] || null;
  },

  isEvaluationRunning: (reportId: number) => {
    return get().runningEvaluations.includes(reportId);
  },

  getRunningEvaluationsCount: () => get().runningEvaluations.length,

  getStudyResult: ( reportId: number, studyId: number) => {
    return get().results[reportId]?.[studyId] || null;
  },

  getResultsForReport: (reportId: number) => {
    return get().results[reportId];
  },

  addStudyResult: (reportId: number, studyId: number, classification: AIClassification, reason: string) => {
    set((state) => {
      const existingResults = state.results[reportId] || {};
      const newReportResults = { ...existingResults, [studyId]: { studyId, classification, reason } };
      return { results: { ...state.results, [reportId]: newReportResults } };
    });
  },

  updateClassification: (reportId: number, studyId: number, classification: AIClassification, reason?: string) => {
    set((state) => {
      const existingResults = state.results[reportId] || {};
      const existing = existingResults[studyId];
      if (existing) {
        const newReportResults = { 
          ...existingResults, 
          [studyId]: { ...existing, classification, reason: reason || existing.reason } 
        };
        return { results: { ...state.results, [reportId]: newReportResults } };
      }
      return state;
    });
  },

  setEvaluationState: (reportId: number, newState: Partial<ReportEvaluationState>) => {
    set((state) => {
      const existing = state.evaluationsByReport[reportId];
      if (existing) {
        return { 
          evaluationsByReport: { 
            ...state.evaluationsByReport, 
            [reportId]: { ...existing, ...newState } 
          } 
        };
      }
      return state;
    });
  },

  startEvaluation: (reportId: number, totalStudies: number) => {
    set((state) => ({
      evaluationsByReport: {
        ...state.evaluationsByReport,
        [reportId]: {
          isStreaming: true,
          streamMessages: [],
          currentMessage: null,
          processedStudies: 0,
          totalStudies,
          error: null,
        },
      },
      runningEvaluations: [...state.runningEvaluations, reportId],
    }));
  },

  endEvaluation: (reportId: number, error?: string) => {
    set((state) => {
      const existing = state.evaluationsByReport[reportId];
      return {
        evaluationsByReport: existing ? {
          ...state.evaluationsByReport,
          [reportId]: { ...existing, isStreaming: false, error: error || null },
        } : state.evaluationsByReport,
        runningEvaluations: state.runningEvaluations.filter(k => k !== reportId),
      };
    });
  },


  evaluateStream: ( report: ReportDto, studies: StudyDto[], options, onStreamComplete) => {
    const { startEvaluation, addStudyResult, updateClassification, setEvaluationState, endEvaluation, streamCleanups } = get();
    const reportId = report.reportId;

    if (streamCleanups[reportId]) {
      streamCleanups[reportId]();
      delete streamCleanups[reportId];
    }

    startEvaluation(reportId, studies.length);

    const abortController = new AbortController();
    const cleanup = () => abortController.abort();

    (async () => {
      try {
        const response = await fetch("/api/genai/evaluate/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            report,
            studies,
            model: options.model || null,
            include_pdf: options.includePdf ?? null,
            prompt_overrides: options.promptOverrides || null,
          }),
          signal: abortController.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(`Stream request failed: ${response.status} ${response.statusText}`);
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
            if (line.startsWith("data: ")) {
              const data = line.slice(6).trim();
              if (!data) continue;
              try {
                const event: StreamEvent = JSON.parse(data);
                // Handle stream event as before
                const currentState = get().evaluationsByReport[reportId];
                setEvaluationState(reportId, {
                  currentMessage: event.message || null,
                  streamMessages: [...(currentState?.streamMessages || []), event],
                });

                if (
                  (
                    event.node === "classify_initial" ||
                    event.node === "classify_unsure" ||
                    event.node === "classify_likely_review"
                  ) &&
                  event.details?.study_id &&
                  event.details?.decision
                ) {
                  const studyId = typeof event.details.study_id === "string"
                    ? parseInt(event.details.study_id)
                    : event.details.study_id;
                  const reason = event.details.reason || "No reason provided";
                  const decision = event.details.decision as AIClassification;

                  if (event.node === "classify_likely_review") {
                    if (decision === "match") {
                      const existingResult = get().results[reportId]?.[studyId];
                      if (existingResult) {
                        updateClassification(reportId, studyId, "match", reason);
                      } else {
                        addStudyResult(reportId, studyId, "match", reason);
                      }
                    } else {
                      const existingResult = get().results[reportId]?.[studyId];
                      if (existingResult) {
                        const stableClassification =
                          existingResult.classification === "very_likely"
                            ? "very_likely"
                            : "likely_match";
                        updateClassification(reportId, studyId, stableClassification, reason);
                      } else {
                        addStudyResult(reportId, studyId, "likely_match", reason);
                      }
                    }
                  } else {
                    addStudyResult(reportId, studyId, decision, reason);
                  }
                }

                if (event.node === "select_very_likely" && event.details?.very_likely_study_ids) {
                  event.details.very_likely_study_ids.forEach((id: string | number) => {
                    const studyId = typeof id === "string" ? parseInt(id) : id;
                    updateClassification(reportId, studyId, "very_likely", event.details?.reason);
                  });
                }

                if (event.node === "compare_very_likely" && event.details?.match_study_id) {
                  const studyId = typeof event.details.match_study_id === "string"
                    ? parseInt(event.details.match_study_id)
                    : event.details.match_study_id;
                  updateClassification(reportId, studyId, "match", event.details.reason);
                }

                if (event.event === "complete") {
                  endEvaluation(reportId);
                  const cleanups = get().streamCleanups;
                  delete cleanups[reportId];
                  set({ streamCleanups: { ...cleanups } });
                  onStreamComplete?.();
                  return;
                }
              } catch (err) {
                // Ignore parse errors for non-JSON lines
              }
            }
          }
        }
        // If we exit the loop without a complete event, treat as error
        endEvaluation(reportId, "Stream ended unexpectedly");
        const cleanups = get().streamCleanups;
        delete cleanups[reportId];
        set({ streamCleanups: { ...cleanups } });
      } catch (error: any) {
        endEvaluation(reportId, error?.message || "Stream error");
        const cleanups = get().streamCleanups;
        delete cleanups[reportId];
        set({ streamCleanups: { ...cleanups } });
      }
    })();

    set((state) => ({ streamCleanups: { ...state.streamCleanups, [reportId]: cleanup } }));
    return cleanup;
  },

  cancelStream: (projectId?: string, reportId?: number) => {
    const { streamCleanups, endEvaluation } = get();
    if (projectId !== undefined && reportId !== undefined) {
      if (streamCleanups[reportId]) {
        streamCleanups[reportId]();
        const newCleanups = { ...streamCleanups };
        delete newCleanups[reportId];
        set({ streamCleanups: newCleanups });
        endEvaluation(reportId);
      }
    } else {
      Object.values(streamCleanups).forEach((cleanup) => cleanup());
      set({ streamCleanups: {}, evaluationsByReport: {}, runningEvaluations: [] });
    }
  },

  clearResults: (projectId?: string, reportId?: number) => {
    if (projectId !== undefined && reportId !== undefined) {
      set((state) => {
        const newResults = { ...state.results };
        delete newResults[reportId];
        return { results: newResults };
      });
    } else {
      set({ results: {} });
    }
  },
}));
