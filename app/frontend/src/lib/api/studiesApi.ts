import apiClient from "./apiClient";
import { unwrap, logAndRethrow } from "./requests";
import { StudyDto, StudyFullDto, ReportPreviewDto, TagDto, Page, GetStudySearchParams } from "../../types/apiDTOs";
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
  };
  return apiClient.get<StudyFullDto>(path, requestConfig)
    .then(unwrap)
    .catch(logAndRethrow('Error fetching study:'));
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
    })
    .then(unwrap)
    .catch(logAndRethrow(`Error searching studies for "${params.q}":`));
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
  };
  return apiClient.get<Page<ReportPreviewDto>>(path, requestConfig)
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching reports for study ${studyId}:`));
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
    })
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching interventions for study ${studyId}:`));
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
      })
      .then(unwrap)
    .catch(logAndRethrow(`Error fetching conditions for study ${studyId}:`));
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
      })
      .then(unwrap)
    .catch(logAndRethrow(`Error fetching outcomes for study ${studyId}:`));
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
      })
      .then(unwrap)
    .catch(logAndRethrow(`Error fetching participants description for study ${studyId}:`));
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
      })
      .then(unwrap)
    .catch(logAndRethrow(`Error fetching design for study ${studyId}:`));
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
