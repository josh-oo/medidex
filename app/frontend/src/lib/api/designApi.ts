import apiClient from "./apiClient";
import { DesignDto } from "../../types/apiDTOs";
import { AxiosRequestConfig } from "axios";

export const getDesigns = (
  config?: AxiosRequestConfig
): Promise<DesignDto[]> => {
  const path = `/design`;
  return apiClient.get<DesignDto[]>(path, config)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error('Error fetching design items:', error);
      throw error;
    });
}
