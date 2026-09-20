import apiClient from "./apiClient";
import { AxiosRequestConfig } from "axios";
import {
  ProjectAnnotationsDto,
  ProjectAssigneeDto,
  ProjectDetailsDto,
  ProjectTaskDto,
  ReportDetailDto,
  StreamCallbacks,
  StreamEvent,
} from "../../types/apiDTOs";

//get all projects
export const getProjects = (config?: AxiosRequestConfig): Promise<ProjectDetailsDto[]> => {
  return apiClient
    .get<ProjectDetailsDto[]>("/projects", config)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error("Error fetching project:", error);
      throw error;
    });
}

//get all projects
export const getTasks = (config?: AxiosRequestConfig): Promise<ProjectTaskDto[]> => {
  return apiClient
    .get<ProjectTaskDto[]>("/tasks", config)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error("Error fetching project:", error);
      throw error;
    });
}

//create a new project by uploading a .ris file
export const createProject = (
  file: File,
  projectName: string,
  config?: AxiosRequestConfig
): Promise<string> => {
  const formData = new FormData();
  formData.append("projectName", projectName)
  formData.append("file", file, file.name);
  
  // The apiClient has a request interceptor that automatically removes Content-Type
  // when FormData is detected, allowing axios to set it with the correct boundary.
  return apiClient.post<string>("/projects", formData, config)
      .then(response => {
          return response.data;
      })
      .catch(error => {
          console.error("Error uploading project:", error);
          // Extract error message from API response
          if (error.response?.data?.detail) {
              const errorMessage = typeof error.response.data.detail === 'string' 
                  ? error.response.data.detail 
                  : JSON.stringify(error.response.data.detail);
              throw new Error(errorMessage);
          }
          throw error;
      });
}

//delete a project by its id
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

//get all report details for a project
export const getProjectReports = (
  projectId: string,
  raw: boolean = false,
  config?: AxiosRequestConfig
): Promise<ReportDetailDto[]> => {
  const requestConfig: AxiosRequestConfig = {
    ...config,
    params: {
      ...config?.params,
      raw: raw,
    },
  };

  return apiClient
    .get<ReportDetailDto[]>(`/projects/${projectId}/reports`, requestConfig)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error(`Error fetching reports for project ${projectId}:`, error);
      throw error;
    });
}

export const getAnnotations = (
  projectId: string,
  config?: AxiosRequestConfig
): Promise<ProjectAnnotationsDto> => {
  return apiClient
    .get<ProjectAnnotationsDto>(`/projects/${projectId}/annotations`, config)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error(`Error fetching annotations for project ${projectId}:`, error);
      throw error;
    });
};

export const assignUserToProject = (
  projectId: string,
  userId: string,
  config?: AxiosRequestConfig
): Promise<ProjectAssigneeDto> => {
  const path = `/projects/${projectId}/assignees`;

  return apiClient
    .post<ProjectAssigneeDto>(path, JSON.stringify(userId), config)
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
              onComplete();
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

      onComplete();
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