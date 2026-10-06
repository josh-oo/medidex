import apiClient from "./apiClient";
import { unwrap, logAndRethrow } from "./requests";
import { AxiosRequestConfig } from "axios";
import { getAccessToken } from "@/lib/client/keycloak";
import {
  GetProjectReportsParams,
  ReportIntakeDto,
  ProjectAnnotationsDto,
  AssigneeDto,
  ProjectDto,
  TaskDto,
  ReportCurationDto,
  Page,
  StreamCallbacks,
  StreamEvent,
} from "../../types/apiDTOs";

//get all projects
export const getProjects = (config?: AxiosRequestConfig): Promise<ProjectDto[]> => {
  return apiClient
    .get<ProjectDto[]>("/projects", config)
    .then(unwrap)
    .catch(logAndRethrow("Error fetching project:"));
}

//get all projects
export const getTasks = (config?: AxiosRequestConfig): Promise<TaskDto[]> => {
  return apiClient
    .get<TaskDto[]>("/tasks", config)
    .then(unwrap)
    .catch(logAndRethrow("Error fetching project:"));
}

export const deleteProjectById = (
  projectId: string,
  config?: AxiosRequestConfig
): Promise<void> => {
  return apiClient
    .delete<void>(`/projects/${projectId}`, config)
    .then(() => {
      return;
    })
    .catch(error => {
      console.error(`Error deleting project with id ${projectId}:`, error);
      throw error;
    });
}

// Three endpoints, one per view, each with only the filter dimensions relevant to it - see
// ReportFiltersState. Readiness is baked into which endpoint you call, not a filter param:
// only /reports/intake (admin-only) ever returns still-processing reports.

//get all fully-processed report details for a project - the normal curation view, available
//to any project assignee (not just admins).
export const getProjectReports = (
  projectId: string,
  filters?: GetProjectReportsParams,
  config?: AxiosRequestConfig
): Promise<Page<ReportCurationDto>> => {
  const requestConfig: AxiosRequestConfig = {
    ...config,
    params: {
      ...config?.params,
      search: filters?.search || undefined,
      processed: filters?.processed,
      flagged: filters?.flagged,
      new_study: filters?.newStudy,
      cursor: filters?.cursor,
      limit: filters?.limit,
      include: filters?.include,
    },
  };

  return apiClient
    .get<Page<ReportCurationDto>>(`/projects/${projectId}/reports`, requestConfig)
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching reports for project ${projectId}:`));
}

//get incoming reports for a project, including still-processing ones - the admin intake view.
export const getProjectReportsIntake = (
  projectId: string,
  filters?: GetProjectReportsParams,
  config?: AxiosRequestConfig
): Promise<Page<ReportIntakeDto>> => {
  const requestConfig: AxiosRequestConfig = {
    ...config,
    params: {
      ...config?.params,
      search: filters?.search || undefined,
      with_pdf: filters?.withPdf,
      cursor: filters?.cursor,
      limit: filters?.limit,
    },
  };

  return apiClient
    .get<Page<ReportIntakeDto>>(`/projects/${projectId}/reports/intake`, requestConfig)
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching intake reports for project ${projectId}:`));
}

//get fully-annotated reports for a project - the admin annotator-review view. Always
//restricted server-side to reports every assignee has completed annotating.
export const getProjectReportsReview = (
  projectId: string,
  filters?: GetProjectReportsParams,
  config?: AxiosRequestConfig
): Promise<Page<ReportCurationDto>> => {
  const requestConfig: AxiosRequestConfig = {
    ...config,
    params: {
      ...config?.params,
      search: filters?.search || undefined,
      consensus: filters?.consensus,
      reviewed: filters?.reviewed,
      cursor: filters?.cursor,
      limit: filters?.limit,
      include: filters?.include,
    },
  };

  return apiClient
    .get<Page<ReportCurationDto>>(`/projects/${projectId}/reports/review`, requestConfig)
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching review reports for project ${projectId}:`));
}

export const getAnnotations = (
  projectId: string,
  config?: AxiosRequestConfig
): Promise<ProjectAnnotationsDto> => {
  return apiClient
    .get<ProjectAnnotationsDto>(`/projects/${projectId}/annotations`, config)
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching annotations for project ${projectId}:`));
};

export const assignUserToProject = (
  projectId: string,
  userId: string,
  config?: AxiosRequestConfig
): Promise<AssigneeDto> => {
  const path = `/projects/${projectId}/assignees`;

  return apiClient
    .post<AssigneeDto>(path, JSON.stringify(userId), config)
    .then(response => response.data)
    .catch(error => {
      console.error(`Error assigning user to project ${projectId}:`, error);
      if (error.response?.data?.detail) {
        const errorMessage = typeof error.response.data.detail === "string"
          ? error.response.data.detail
          : JSON.stringify(error.response.data.detail);
        throw new Error(errorMessage);
      }
      throw error;
    });
};

export const removeUserFromProject = (
  projectId: string,
  userId: string,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/projects/${projectId}/assignees/${userId}`;

  return apiClient
    .delete<void>(path, config)
    .then(() => undefined)
    .catch(error => {
      console.error(`Error removing user ${userId} from project ${projectId}:`, error);
      if (error.response?.data?.detail) {
        const errorMessage = typeof error.response.data.detail === "string"
          ? error.response.data.detail
          : JSON.stringify(error.response.data.detail);
        throw new Error(errorMessage);
      }
      throw error;
    });
};

export const streamProjectUpdates = (
  projectId: string,
  callbacks: StreamCallbacks,
  config?: AxiosRequestConfig
): (() => void) => {
  const { onEvent, onComplete, onError } = callbacks;
  const abortController = new AbortController();

  const path = `/projects/${projectId}/stream`;
  const baseURL = apiClient.defaults.baseURL ?? "";
  const url = `${baseURL}${path}`;

  const headers: Record<string, string> = {
    Accept: "text/event-stream",
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
      const token = await getAccessToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }

      const response = await fetch(url, {
        method: "GET",
        headers,
        signal: abortController.signal,
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(
          `Project stream request failed: ${response.status} ${response.statusText}. ${errorText}`
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
          if (!line.startsWith("data:")) {
            continue;
          }

          const data = line.slice(5).trim();

          if (!data) {
            continue;
          }

          try {
            const parsed = JSON.parse(data) as Partial<StreamEvent>;

            if (parsed.event === "complete") {
              onComplete?.();
              return;
            }

            const streamEvent: StreamEvent = {
              event: parsed.event ?? "unknown",
              node: parsed.node,
              message: parsed.message,
              details: parsed.details,
              timestamp: Date.now(),
            };

            onEvent(streamEvent);
          } catch {
            const streamEvent: StreamEvent = {
              event: "unknown",
              message: data,
              timestamp: Date.now(),
            };

            onEvent(streamEvent);
          }
        }
      }

      onComplete?.();
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        return;
      }

      console.error(`Error streaming updates for project ${projectId}:`, error);
      onError(
        error instanceof Error
          ? error
          : new Error("Unknown project stream error occurred")
      );
    }
  };

  startStream();

  return () => {
    abortController.abort();
  };
};
