import apiClient from "./apiClient";
import { unwrap, logAndRethrow } from "./requests";
import { StudyDto, StudyFullDto, StudySchemaDto, StudyViewDto, ReportPreviewDto, TagDto, Page, GetStudySearchParams } from "../../types/apiDTOs";
import { AxiosRequestConfig } from "axios";

// Full study details in one call - linked reports plus the tags of each category of the
// study schema, each as a first page (limit, default 10 on the backend). Page further
// through any one of them via its own dedicated endpoint below (getReportsByStudyId,
// getTagsForStudy) and its nextCursor.
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

// One page of the tags of a category of the study schema (see getStudySchema) of a study.
export const getTagsForStudy = (
  studyId: number,
  category: string,
  limit?: number,
  cursor?: string | null,
  config?: AxiosRequestConfig
): Promise<Page<TagDto>> => {
  const path = `/studies/${studyId}/${category}`;
  return apiClient.get<Page<TagDto>>(path, {
      ...config,
      params: { limit, cursor: cursor ?? undefined },
    })
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching ${category} for study ${studyId}:`));
}

// What a study consists of and how it is presented; the same for every study.
export const getStudySchema = (config?: AxiosRequestConfig): Promise<StudySchemaDto> =>
  apiClient.get<StudySchemaDto>("/study-schema", config)
    .then(unwrap)
    .catch(logAndRethrow("Error fetching the study schema:"));

// The views (see the study schema) of studies, by study, each with its tags named.
export const getStudyViews = (studyIds: number[]): Promise<Record<number, Record<string, StudyViewDto>>> =>
  apiClient
    .get<Record<number, Record<string, StudyViewDto>>>(`/studies/views?${studyIds.map((id) => `study_ids=${id}`).join("&")}`)
    .then(unwrap)
    .catch(logAndRethrow("Error fetching the views of studies:"));

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
