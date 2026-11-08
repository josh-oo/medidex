import apiClient from "./apiClient";
import { unwrap, logAndRethrow } from "./requests";
import { AxiosRequestConfig } from "axios";
import { getAccessToken } from "@/lib/client/keycloak";
import { uploadFile } from "./databaseApi";
import {
  GetProjectReportsParams,
  ReportIntakeDto,
  ProjectAnnotationsDto,
  AssigneeDto,
  ProjectDto,
  TaskDto,
  ReportCurationDto,
  Page,
} from "../../types/apiDTOs";

// The bundle of an update: a .zip with update.json and the PDFs of its reports.
export const isUpdateBundle = (file: File): boolean => file.name.toLowerCase().endsWith(".zip");

// A new project (an update of a database) with the reports of a bibliography file (.ris, .nbib) or of the bundle of an
// update. A bundle holds PDFs and may be larger than a proxy lets through in one request, so it is uploaded with tus
// first and named by its upload. `onUpload` gets how many of the file's bytes are sent.
export const createProject = async (
  file: File,
  fields: { projectName: string; databaseId: number; options: Record<string, unknown> },
  onUpload?: (loaded: number, total: number) => void,
): Promise<ProjectDto> => {
  try {
    const formData = new FormData();
    formData.append("projectName", fields.projectName);
    formData.append("databaseId", String(fields.databaseId));
    formData.append("options", JSON.stringify(fields.options));
    if (isUpdateBundle(file)) {
      formData.append("uploadId", await uploadFile(file, onUpload));
      return unwrap(await apiClient.post<ProjectDto>("/projects", formData));
    }
    formData.append("file", file, file.name);
    return unwrap(
      await apiClient.post<ProjectDto>("/projects", formData, {
        onUploadProgress: (event) => onUpload?.(event.loaded, event.total ?? file.size),
      }),
    );
  } catch (error) {
    return logAndRethrow("Error creating project:")(error);
  }
};

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
      include: filters?.include,
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

// The caller hands in their links of the project: they cannot change them any more, and once every assignee has, the
// project is locked for its owner to merge them.
export const commitProjectWork = (projectId: string, config?: AxiosRequestConfig): Promise<void> => {
  const path = `/projects/${projectId}/commit`;

  return apiClient
    .post<void>(path, undefined, config)
    .then(() => undefined)
    .catch(error => {
      console.error(`Error committing the links of project ${projectId}:`, error);
      if (error.response?.data?.detail) {
        const errorMessage = typeof error.response.data.detail === "string"
          ? error.response.data.detail
          : JSON.stringify(error.response.data.detail);
        throw new Error(errorMessage);
      }
      throw error;
    });
};

// The project as /projects returns it, at once and whenever what it shows changes (its progress, its assignees, their
// commits). Returns a function that stops the stream.
export const streamProjectUpdates = (
  projectId: string,
  onProject: (project: ProjectDto) => void,
  onError?: (error: Error) => void
): (() => void) => {
  const abortController = new AbortController();
  const url = `${apiClient.defaults.baseURL ?? ""}/projects/${projectId}/stream`;

  const startStream = async () => {
    try {
      const headers: Record<string, string> = { Accept: "text/event-stream" };
      const token = await getAccessToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const response = await fetch(url, { headers, signal: abortController.signal });
      if (!response.ok || !response.body) {
        throw new Error(`Project stream request failed: ${response.status} ${response.statusText}`);
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
          const data = line.startsWith("data:") ? line.slice(5).trim() : "";
          if (data) onProject(JSON.parse(data) as ProjectDto);
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      console.error(`Error streaming updates for project ${projectId}:`, error);
      onError?.(error instanceof Error ? error : new Error("Unknown project stream error occurred"));
    }
  };

  void startStream();
  return () => abortController.abort();
};

// The intake row of every report of a project that changes (an uploaded PDF, a finished postprocessing), as
// /reports/intake returns it with the same `include`. Returns a function that stops the stream.
export const streamProjectIntakeUpdates = (
  projectId: string,
  onReport: (report: ReportIntakeDto) => void,
  include?: string[]
): (() => void) => {
  const abortController = new AbortController();
  const params = new URLSearchParams();
  include?.forEach((key) => params.append("include", key));
  const url = `${apiClient.defaults.baseURL ?? ""}/projects/${projectId}/reports/intake/stream?${params}`;

  const startStream = async () => {
    try {
      const headers: Record<string, string> = { Accept: "text/event-stream" };
      const token = await getAccessToken();
      if (token) {
        headers.Authorization = `Bearer ${token}`;
      }
      const response = await fetch(url, { headers, signal: abortController.signal });
      if (!response.ok || !response.body) {
        throw new Error(`Intake stream request failed: ${response.status} ${response.statusText}`);
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
          const data = line.startsWith("data:") ? line.slice(5).trim() : "";
          if (data) onReport(JSON.parse(data) as ReportIntakeDto);
        }
      }
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") return;
      console.error(`Error streaming the reports of project ${projectId}:`, error);
    }
  };

  void startStream();
  return () => abortController.abort();
};
