import apiClient from "./apiClient";
import { AxiosRequestConfig } from "axios";
import type {
  EvaluateRequest,
  StreamEvent,
  StreamCallbacks,
} from "@/types/apiDTOs";


export const evaluateStudiesStream = (
  request: EvaluateRequest,
  callbacks: StreamCallbacks,
  config?: AxiosRequestConfig
): (() => void) => {
  const { onEvent, onComplete, onError } = callbacks;
  const abortController = new AbortController();

  const path = "/evaluate/stream";
  const baseURL = apiClient.defaults.baseURL ?? "";
  const url = `${baseURL}${path}`;

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (config?.headers) {
    Object.entries(config.headers as Record<string, unknown>).forEach(([k, v]) => {
      if (v !== null && v !== undefined) {
        headers[k] = String(v);
      }
    });
  }

  const startStream = async () => {
    try {
      const response = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify(request),
        signal: abortController.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `Stream request failed: ${response.status} ${response.statusText}. ${errorText}`
        );
      }

      if (!response.body) {
        throw new Error("Response body is null");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6).trim();

            if (!data) continue;

            try {
              const parsed = JSON.parse(data);

              if (parsed.event === "complete") {
                onComplete();
                return;
              }

              const streamEvent: StreamEvent = {
                event: parsed.event || "unknown",
                node: parsed.node,
                message: parsed.message,
                details: parsed.details,
                timestamp: Date.now(),
              };

              onEvent(streamEvent);
            } catch (parseError) {
              console.error("Failed to parse SSE data:", data, parseError);
            }
          }
        }
      }

      onComplete();
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }

      console.error("Stream error:", error);
      onError(
        error instanceof Error
          ? error
          : new Error("Unknown stream error occurred")
      );
    }
  };

  startStream();

  return () => {
    abortController.abort();
  };
};
