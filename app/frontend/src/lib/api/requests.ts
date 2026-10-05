import type { AxiosRequestConfig, AxiosResponse } from "axios";
import apiClient from "./apiClient";

export const unwrap = <T>(response: AxiosResponse<T>): T => response.data;

/**
 * Catch handler that logs `message` with the error and rethrows it. With `messageOnly` it logs
 * just the error's message when it has one (e.g. to keep large axios errors out of the console).
 */
export const logAndRethrow =
  (message: string, messageOnly = false) =>
  (error: unknown): never => {
    const detail = messageOnly && error instanceof Error && error.message ? error.message : error;
    console.error(message, detail);
    throw error;
  };

/** Builds a `GET <path>` fetcher that returns the response body as a list. */
export const listGetter =
  <T>(path: string, label: string) =>
  (config?: AxiosRequestConfig): Promise<T[]> =>
    apiClient
      .get<T[]>(path, config)
      .then(unwrap)
      .catch(logAndRethrow(`Error fetching ${label}:`));
