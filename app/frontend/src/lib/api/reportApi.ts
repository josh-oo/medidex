import apiClient from "./apiClient";
import { AxiosRequestConfig } from "axios";
import { ReportChatDto, ReportSourcesDto, SimilarTagDto, SimilarStudyDto, GetSimilarStudiesParams, GetSimilarTagsParams, StudyDto} from "../../types/apiDTOs";
import { serializeParams } from "./helpers";    

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
): Promise<SimilarStudyDto[]> => { 
  const path = `/reports/${reportId}/similar-studies`;
  const { params: configParams, ...restConfig } = config ?? {};
  const requestParams = {
    ...(configParams ?? {}),
    ...params,
  };
  return apiClient.get<SimilarStudyDto[]>(path, {
      ...restConfig,
      params: requestParams,
      paramsSerializer: { serialize: serializeParams }
    })
    .then(response => {
    return response.data;
    })
    .catch(error => {
    console.error(`Error fetching similar studies for report ${reportId}:`, error);
    throw error;
    });
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
    paramsSerializer: { serialize: serializeParams } 
  };
  return apiClient.put<void>(path, null, requestConfig).then(response => response.data);
}

export const confirmStudyForReportByReportId = (
  reportId: number,
  studyId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/studies/${studyId}/confirmation`;
  const requestConfig = {
    ...config,
    paramsSerializer: { serialize: serializeParams }
  };

  return apiClient.put<void>(path, null, requestConfig).then(response => response.data);
}

export const unconfirmStudyForReportByReportId = (
  reportId: number,
  studyId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/studies/${studyId}/confirmation`;

  return apiClient
    .delete<void>(path, config)
    .then(response => response.data)
    .catch(error => {
      console.error(`Error removing confirmation for study ${studyId} in report ${reportId}:`, error);
      throw error;
    });
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
    .then(response => {
      return;
    })
    .catch(error => {
      console.error(`Error removing studies from report ${reportId}:`, error);
      throw error;
    });
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
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error(`Error assigning new study to report ${reportId}:`, error);
      throw error;
    });
}

//remove studies from a report
export const getSimilarTagsByReportId = (
  reportId: number,
  params: GetSimilarTagsParams = {},
  config?: AxiosRequestConfig
): Promise<SimilarTagDto[]> => {
  const path = `/reports/${reportId}/similar-studies/tags`;
  const { params: configParams, ...restConfig } = config ?? {};
  const requestParams = {
    ...(configParams ?? {}),
    ...params,
  };
  return apiClient.get<SimilarTagDto[]>(path, {
      ...restConfig,
      params: requestParams,
      paramsSerializer: { serialize: serializeParams }
    })
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error(`Error fetching similar studies for report ${reportId}:`, error);
      throw error;
    });
}

export const getStudiesByReportId = (
  reportId: number,
  params?: { date_from?: string | null; date_to?: string | null },
  config?: AxiosRequestConfig
): Promise<StudyDto[]> => {
  const path = `/reports/${reportId}/studies`;

  const requestConfig: AxiosRequestConfig = {
    ...config,
    params: params,
    paramsSerializer: { serialize: serializeParams },
  };

  return apiClient
    .get<StudyDto[]>(path, requestConfig)
    .then((response) => response.data)
    .catch((error) => {
      console.error(
        `Error fetching studies for report ${reportId}:`,
        error.message || error
      );
      throw error;
    });
};

export const getReportPdf = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<ArrayBuffer> => {
  const path = `/reports/${reportId}/pdf`;
  return apiClient.get<ArrayBuffer>(path, { responseType: 'arraybuffer', ...config })
    .then(response => {
      return response.data;
    })  
    .catch(error => {
      console.error(`Error fetching PDF for report ${reportId}:`, error.message || error);
      throw error;
    });
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
    .then(() => {})
    .catch(error => {
      console.error(`Error fetching PDF for report ${reportId}:`, error.message || error);
      throw error;
    });
}

export const deleteReportPdf = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/pdf`;
  return apiClient
    .delete<void>(path, config)
    .then(() => {})
    .catch(error => {
      console.error(`Error deleting PDF for report ${reportId}:`, error.message || error);
      throw error;
    });
};

export const getReportSources = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<ReportSourcesDto> => {
  const path = `/reports/${reportId}/sources`;
  return apiClient.get<ReportSourcesDto>(path, config)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error(`Error fetching links for report ${reportId}:`, error.message || error);
      throw error;
    });
}

export const getReportChat = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<ReportChatDto> => {
  const path = `/reports/${reportId}/chat`;
  return apiClient
    .get<ReportChatDto>(path, config)
    .then((response) => response.data)
    .catch((error) => {
      console.error(`Error fetching chat for report ${reportId}:`, error.message || error);
      throw error;
    });
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
    .then((response) => response.data)
    .catch((error) => {
      console.error(`Error posting chat message for report ${reportId}:`, error.message || error);
      throw error;
    });
}

export const deleteReportChat = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/chat`;
  return apiClient
    .delete<void>(path, config)
    .then(() => {})
    .catch((error) => {
      console.error(`Error deleting chat for report ${reportId}:`, error.message || error);
      throw error;
    });
}

export const getReportFlagByReportId = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<ReportFlagDto | null> => {
  const path = `/reports/${reportId}/flag`;
  return apiClient
    .get<ReportFlagDto | null>(path, config)
    .then((response) => response.data)
    .catch((error) => {
      console.error(`Error fetching flag for report ${reportId}:`, error.message || error);
      throw error;
    });
}

export const upsertReportFlagByReportId = (
  reportId: number,
  payload: ReportFlagUpsertPayload,
  config?: AxiosRequestConfig
): Promise<ReportFlagDto> => {
  const path = `/reports/${reportId}/flag`;
  return apiClient
    .put<ReportFlagDto>(path, payload, config)
    .then((response) => response.data)
    .catch((error) => {
      console.error(`Error upserting flag for report ${reportId}:`, error.message || error);
      throw error;
    });
}

export const deleteReportFlagByReportId = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}/flag`;
  return apiClient
    .delete<void>(path, config)
    .then(() => {})
    .catch((error) => {
      console.error(`Error deleting flag for report ${reportId}:`, error.message || error);
      throw error;
    });
}

export const deleteReportById = (
  reportId: number,
  config?: AxiosRequestConfig
): Promise<void> => {
  const path = `/reports/${reportId}`;
  return apiClient
    .delete<void>(path, config)
    .then(() => {})
    .catch((error) => {
      console.error(`Error deleting report ${reportId}:`, error.message || error);
      throw error;
    });
};