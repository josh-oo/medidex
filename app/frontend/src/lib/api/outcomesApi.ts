import apiClient from "./apiClient";
import { TagDto } from "../../types/apiDTOs";
import { AxiosRequestConfig } from "axios";

export const getOutcomes = (
  config?: AxiosRequestConfig
): Promise<TagDto[]> => {
  const path = `/outcomes`;
  return apiClient.get<TagDto[]>(path, config)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error('Error fetching outcomes:', error);
      throw error;
    });
}
