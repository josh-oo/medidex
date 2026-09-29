import apiClient from "./apiClient";
import { TagDto } from "../../types/apiDTOs";
import { AxiosRequestConfig } from "axios";

export const getInterventions = (
  config?: AxiosRequestConfig
): Promise<TagDto[]> => {
  const path = `/interventions`;
  return apiClient.get<TagDto[]>(path, config)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error('Error fetching interventions:', error);
      throw error;
    });
}
