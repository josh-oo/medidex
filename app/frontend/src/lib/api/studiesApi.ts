import apiClient from "./apiClient";
import { StudyDto, StudyFullDto, StudyBaseDto , ReportPreviewDto, TagDto, GetPersonsResponseDto, Page, GetStudySearchParams } from "../../types/apiDTOs";
import { serializeParams } from "./helpers";
import { AxiosRequestConfig } from "axios";

// Full study details in one call - linked reports plus interventions/conditions/
// outcomes/participants/design, each as a first page (limit, default 10 on the
// backend). Page further through any one of them via its own dedicated endpoint
// below (getReportsByStudyId, getInterventionsForStudy, ...) and its nextCursor.
export const getStudyById = (
  studyId: number,
  limit?: number,
  config?: AxiosRequestConfig
): Promise<StudyFullDto> => {
  const path = `/studies/${studyId}`;

  const requestConfig = {
    ...config,
    params: { limit },
    paramsSerializer: {
      serialize: serializeParams,
    },
  };
  return apiClient.get<StudyFullDto>(path, requestConfig)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error('Error fetching study:', error);
      throw error;
    });
}

export const searchStudies = (
  params: GetStudySearchParams,
  config?: AxiosRequestConfig
): Promise<Page<StudyDto>> => {
  const { params: configParams, ...restConfig } = config ?? {};
  const requestParams = {
    ...(configParams ?? {}),
    ...params,
  };

  // the plain study listing doubles as the search when given `q`
  return apiClient.get<Page<StudyDto>>("/studies", {
      ...restConfig,
      params: requestParams,
      paramsSerializer: { serialize: serializeParams },
    })
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error(`Error searching studies for "${params.q}":`, error);
      throw error;
    });
}

export const getReportsByStudyId = (
  studyId: number,
  limit?: number,
  cursor?: string | null,
  config?: AxiosRequestConfig
): Promise<Page<ReportPreviewDto>> => {
  const path = `/studies/${studyId}/reports`;

  const requestConfig = {
    ...config,
    params: {
      limit,
      cursor: cursor ?? undefined,
    },
    paramsSerializer: {
      serialize: serializeParams,
    },
  };
  return apiClient.get<Page<ReportPreviewDto>>(path, requestConfig)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error(`Error fetching reports for study ${studyId}:`, error);
      throw error;
    });
}

export const getInterventionsForStudy = (
  studyId: number,
  limit?: number,
  cursor?: string | null,
  config?: AxiosRequestConfig
): Promise<Page<TagDto>> => {
  const path = `/studies/${studyId}/interventions`;
  return apiClient.get<Page<TagDto>>(path, {
      ...config,
      params: { limit, cursor: cursor ?? undefined },
      paramsSerializer: { serialize: serializeParams },
    })
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error(`Error fetching interventions for study ${studyId}:`, error);
      throw error;
    });
}

export const getConditionsForStudy = (
  studyId: number,
  limit?: number,
  cursor?: string | null,
  config?: AxiosRequestConfig
): Promise<Page<TagDto>> => {
    const path = `/studies/${studyId}/conditions`;
    return apiClient.get<Page<TagDto>>(path, {
        ...config,
        params: { limit, cursor: cursor ?? undefined },
        paramsSerializer: { serialize: serializeParams },
      })
      .then(response => {
        return response.data;
      })
      .catch(error => {
        console.error(`Error fetching conditions for study ${studyId}:`, error);
        throw error;
      });
}

export const getOutcomesForStudy = (
  studyId: number,
  limit?: number,
  cursor?: string | null,
  config?: AxiosRequestConfig
): Promise<Page<TagDto>> => {
    const path = `/studies/${studyId}/outcomes`;
    return apiClient.get<Page<TagDto>>(path, {
        ...config,
        params: { limit, cursor: cursor ?? undefined },
        paramsSerializer: { serialize: serializeParams },
      })
      .then(response => {
        return response.data;
      })
      .catch(error => {
        console.error(`Error fetching outcomes for study ${studyId}:`, error);
        throw error;
      });
}

//get participants description for a study
export const getParticipantsForStudy = (
  studyId: number,
  limit?: number,
  cursor?: string | null,
  config?: AxiosRequestConfig
): Promise<Page<TagDto>> => {
    const path = `/studies/${studyId}/participants`;
    return apiClient.get<Page<TagDto>>(path, {
        ...config,
        params: { limit, cursor: cursor ?? undefined },
        paramsSerializer: { serialize: serializeParams },
      })
      .then(response => {
        return response.data;
      })
      .catch(error => {
        console.error(`Error fetching participants description for study ${studyId}:`, error);
        throw error;
      });
}

export const getDesignForStudy = (
  studyId: number,
  limit?: number,
  cursor?: string | null,
  config?: AxiosRequestConfig
): Promise<Page<TagDto>> => {
    const path = `/studies/${studyId}/design`;
    return apiClient.get<Page<TagDto>>(path, {
        ...config,
        params: { limit, cursor: cursor ?? undefined },
        paramsSerializer: { serialize: serializeParams },
      })
      .then(response => {
        return response.data;
      })
      .catch(error => {
        console.error(`Error fetching design for study ${studyId}:`, error);
        throw error;
      });
}

export const getPersonsForStudy = (
  studyId: number,
  config?: AxiosRequestConfig
): Promise<string[]> => {  
  const path = `/studies/${studyId}/persons`;
  return apiClient.get<string[]>(path, config)
    .then(response => {
      return response.data || [];
    })
    .catch(error => {
      console.error(`Error fetching persons for study ${studyId}:`, error);
      throw error;
    });
};

export const createStudy = (
  payload: StudyBaseDto,
  config?: AxiosRequestConfig
): Promise<StudyDto> => {
  return apiClient
    .put<StudyDto>("/studies", payload, config)
    .then((response) => response.data)
    .catch((error) => {
      console.error("Error creating study:", error);
      if (error.response?.data?.detail) {
        const detail = error.response.data.detail;
        const message =
          typeof detail === "string" ? detail : JSON.stringify(detail);
        throw new Error(message);
      }
      throw error;
    });
};
