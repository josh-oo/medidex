import apiClient from "./apiClient";
import { StudyDto, StudyCreateDto , ReportDto, InterventionDto, ConditionDto, OutcomeDto , GetPersonsResponseDto } from "../../types/apiDTOs";
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
  query: string,
  config?: AxiosRequestConfig
): Promise<StudyDto[]> => {
  const requestConfig = {
    ...config,
    params: {
      ...config?.params,
      q: query,
    },
    paramsSerializer: {
      serialize: serializeParams,
    },
  };

  return apiClient.get<StudyDto[]>("/studies", requestConfig)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error(`Error searching studies for "${query}":`, error);
      throw error;
    });
}

export const getReportsByStudyId = (
  studyId: number,
  includePdfLinks?: boolean,
  config?: AxiosRequestConfig
): Promise<ReportDto[]> => {
  const path = `/studies/${studyId}/reports`;

  const requestConfig = {
    ...config,
    params: {
      include_pdf_links: includePdfLinks,
    },
    paramsSerializer: {
      serialize: serializeParams,
    },
  };
  return apiClient.get<ReportDto[]>(path, requestConfig)
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
): Promise<InterventionDto[]> => {
  const path = `/studies/${studyId}/interventions`;
  return apiClient.get<InterventionDto[]>(path, config)
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
): Promise<ConditionDto[]> => {
    const path = `/studies/${studyId}/conditions`;
    return apiClient.get<ConditionDto[]>(path, config)
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
): Promise<OutcomeDto[]> => {
    const path = `/studies/${studyId}/outcomes`;
    return apiClient.get<OutcomeDto[]>(path, config)
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
  payload: StudyCreateDto,
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
