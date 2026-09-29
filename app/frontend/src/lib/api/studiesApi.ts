import apiClient from "./apiClient";
import { StudyDto, StudyBaseDto , ReportPreviewDto, TagDto, GetPersonsResponseDto, Page, GetStudySearchParams } from "../../types/apiDTOs";
import { serializeParams } from "./helpers";
import { AxiosRequestConfig } from "axios";

export const getStudyById = (
  studyId: number,
  config?: AxiosRequestConfig
): Promise<StudyDto> => {
  const path = `/studies/${studyId}`;

  const requestConfig = {
    ...config,
    paramsSerializer: {
      serialize: serializeParams,
    },
  };
  return apiClient.get<StudyDto>(path, requestConfig)
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

  return apiClient.get<Page<StudyDto>>("/studies/search", {
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
  config?: AxiosRequestConfig
): Promise<TagDto[]> => {
  const path = `/studies/${studyId}/interventions`;
  return apiClient.get<TagDto[]>(path, config)
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
  config?: AxiosRequestConfig
): Promise<TagDto[]> => {
    const path = `/studies/${studyId}/conditions`;
    return apiClient.get<TagDto[]>(path, config)
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
  config?: AxiosRequestConfig
): Promise<TagDto[]> => {
    const path = `/studies/${studyId}/outcomes`;
    return apiClient.get<TagDto[]>(path, config)
      .then(response => {
        return response.data;
      })
      .catch(error => {
        console.error(`Error fetching outcomes for study ${studyId}:`, error);
        throw error;
      });
}

//get participants description for a study
export const getParticipantsForStudy = (studyId: number): Promise<string[]> => {
    const path = `/studies/${studyId}/participants`;
    return apiClient.get<string[]>(path)
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
  config?: AxiosRequestConfig
): Promise<string[]> => {
    const path = `/studies/${studyId}/design`;
    return apiClient.get<string[]>(path, config)
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
