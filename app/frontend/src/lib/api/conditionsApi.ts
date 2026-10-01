import apiClient from "./apiClient";
import { TagDto } from "../../types/apiDTOs";
import { AxiosRequestConfig } from "axios";

export const getConditions = (
  config?: AxiosRequestConfig
): Promise<TagDto[]> => {
  const path = `/conditions`;
  return apiClient.get<TagDto[]>(path, config)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error('Error fetching conditions:', error);
      throw error;
    });
}
