import apiClient from "./apiClient";
import { unwrap, logAndRethrow } from "./requests";
import { AxiosRequestConfig } from "axios";
import { ReportChatDto, TagCandidateDto, StudyCandidateDto, Page, GetSimilarStudiesParams, GetSimilarTagsParams, StudyDto} from "../../types/apiDTOs";

export interface ReportFlagDto {
  message: string;
  public: boolean;
}

export interface ReportFlagUpsertPayload {
  message: string;
  public: boolean;
}

export const getSimilarStudiesByReportId = (
  reportId: number,
  params: GetSimilarStudiesParams = {},
  config?: AxiosRequestConfig
): Promise<Page<StudyCandidateDto>> => {
  const path = `/reports/${reportId}/similar-studies`;
  const { params: configParams, ...restConfig } = config ?? {};
  const requestParams = {
    ...(configParams ?? {}),
    ...params,
  };
  return apiClient.get<Page<StudyCandidateDto>>(path, {
      ...restConfig,
      params: requestParams,
    })
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching similar studies for report ${reportId}:`));
}

// studies of reports in the database whose DOI the given report cites
export const getReferencedStudiesByReportId = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<StudyCandidateDto[]> => {
  return apiClient.get<StudyCandidateDto[]>(`/reports/${reportId}/referenced-studies`, config)
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching referenced studies for report ${reportId}:`));
}

//assign studies to a report
export const assignStudyToReportByReportId = (
  reportId: number,
  studyId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/studies/${studyId}`;
  const requestConfig = {
    ...config,
  };
  return apiClient.put<void>(path, null, requestConfig).then(unwrap);
}

export const confirmStudyForReportByReportId = (
  reportId: number,
  studyId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/studies/${studyId}/confirmation`;
  const requestConfig = {
    ...config,
  };

  return apiClient.put<void>(path, null, requestConfig).then(unwrap);
}

export const unconfirmStudyForReportByReportId = (
  reportId: number,
  studyId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/studies/${studyId}/confirmation`;

  return apiClient
    .delete<void>(path, config)
    .then(unwrap)
    .catch(logAndRethrow(`Error removing confirmation for study ${studyId} in report ${reportId}:`));
}

//remove studies from a report
export const removeStudyFromReportByReportId = (
  reportId: number,
  studyId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/studies/${studyId}`;
  return apiClient
    .delete<void>(path, config)
    .then(() => undefined)
    .catch(logAndRethrow(`Error removing studies from report ${reportId}:`));
}

//create and assign a brand-new study to a report
export const assignNewStudyToReportByReportId = (
  reportId: number,
  study: StudyDto,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/studies`;
  return apiClient
    .post<void>(path, study, config)
    .then(unwrap)
    .catch(logAndRethrow(`Error assigning new study to report ${reportId}:`));
}

//remove studies from a report
export const getSimilarTagsByReportId = (
  reportId: number,
  params: GetSimilarTagsParams = {},
  config?: AxiosRequestConfig
): Promise<TagCandidateDto[]> => {
  const path = `/reports/${reportId}/similar-studies/tags`;
  const { params: configParams, ...restConfig } = config ?? {};
  const requestParams = {
    ...(configParams ?? {}),
    ...params,
  };
  return apiClient.get<TagCandidateDto[]>(path, {
      ...restConfig,
      params: requestParams,
    })
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching similar studies for report ${reportId}:`));
}

export const getReportPdf = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<ArrayBuffer> => {
  const path = `/reports/${reportId}/pdf`;
  return apiClient.get<ArrayBuffer>(path, { responseType: 'arraybuffer', ...config })
    .then(response => {
      return response.data;
    })  
    .catch(logAndRethrow(`Error fetching PDF for report ${reportId}:`, true));
}

export const uploadPdf = (
  reportId: number,
  file: File | null,
  config?: AxiosRequestConfig
): Promise<void> => {

  const formData = new FormData();
  if (file){
    formData.append("file", file, file.name);
  }

  const path = `/reports/${reportId}/pdf`;
  return apiClient.put<void>(path, formData, config)
    .then(() => undefined)
    .catch(logAndRethrow(`Error fetching PDF for report ${reportId}:`, true));
}

export const deleteReportPdf = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/pdf`;
  return apiClient
    .delete<void>(path, config)
    .then(() => undefined)
    .catch(logAndRethrow(`Error deleting PDF for report ${reportId}:`, true));
};

export const getReportChat = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<ReportChatDto> => {
  const path = `/reports/${reportId}/chat`;
  return apiClient
    .get<ReportChatDto>(path, config)
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching chat for report ${reportId}:`, true));
}

export const postReportChat = (
  reportId: number,
  message: string,
  config?: AxiosRequestConfig
): Promise<ReportChatDto> => {
  const path = `/reports/${reportId}/chat`;
  const requestConfig: AxiosRequestConfig = {
    ...config,
    headers: {
      "Content-Type": "text/plain",
      ...config?.headers,
    },
  };

  return apiClient
    .post<ReportChatDto>(path, message, requestConfig)
    .then(unwrap)
    .catch(logAndRethrow(`Error posting chat message for report ${reportId}:`, true));
}

export const deleteReportChat = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/chat`;
  return apiClient
    .delete<void>(path, config)
    .then(() => undefined)
    .catch(logAndRethrow(`Error deleting chat for report ${reportId}:`, true));
}

export const getReportFlagByReportId = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<ReportFlagDto | null> => {
  const path = `/reports/${reportId}/flag`;
  return apiClient
    .get<ReportFlagDto | null>(path, config)
    .then(unwrap)
    .catch(logAndRethrow(`Error fetching flag for report ${reportId}:`, true));
}

export const upsertReportFlagByReportId = (
  reportId: number,
  payload: ReportFlagUpsertPayload,
  config?: AxiosRequestConfig
): Promise<ReportFlagDto> => {
  const path = `/reports/${reportId}/flag`;
  return apiClient
    .put<ReportFlagDto>(path, payload, config)
    .then(unwrap)
    .catch(logAndRethrow(`Error upserting flag for report ${reportId}:`, true));
}

export const deleteReportFlagByReportId = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/flag`;
  return apiClient
    .delete<void>(path, config)
    .then(() => undefined)
    .catch(logAndRethrow(`Error deleting flag for report ${reportId}:`, true));
}

export const deleteReportById = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}`;
  return apiClient
    .delete<void>(path, config)
    .then(() => undefined)
    .catch(logAndRethrow(`Error deleting report ${reportId}:`, true));
};
