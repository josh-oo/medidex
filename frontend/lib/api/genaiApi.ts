import apiClient from "./apiClient";
import { AxiosRequestConfig } from "axios";
import type { DefaultPrompts, EvaluateRequest, EvaluateResponse } from "@/types/apiDTOs";

let cachedDefaultPrompts: DefaultPrompts | null = null;
/**
 * Evaluates a report against a list of studies using AI to find matches.
 * 
 * @param request - Contains the report, studies to evaluate, and optional AI settings
 * @returns Evaluation response with matched, likely matches, unsure, and not matched studies
 */
export const evaluateStudies = async (
  request: EvaluateRequest,
  config?: AxiosRequestConfig
): Promise<EvaluateResponse> => {
  const path = `/evaluate`;
  return apiClient
      .post<EvaluateResponse>(path, request, config)
      .then(response => {
        return response.data;
      })
      .catch(error => {
        console.error(`Error evaluating studies`, error);
        throw error;
      });
};

export const fetchDefaultPrompts = async (
  config?: AxiosRequestConfig
): Promise<DefaultPrompts> => {
  
  if (cachedDefaultPrompts) {
    return cachedDefaultPrompts;
  }

  const path = `/prompts`;
  return apiClient
      .get<DefaultPrompts>(path, config)
      .then(response => {
        cachedDefaultPrompts = response.data;
        return response.data;
      })
      .catch(error => {
        console.error(`Error getting default prompts`, error);
        throw error;
      });
};
