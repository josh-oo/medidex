import apiClient from "./apiClient";
import { ParticipantDto } from "../../types/apiDTOs";
import { AxiosRequestConfig } from "axios";

export const getParticipants = (
  config?: AxiosRequestConfig
): Promise<ParticipantDto[]> => {
  const path = `/participants`;
  return apiClient.get<ParticipantDto[]>(path, config)
    .then(response => {
      return response.data;
    })
    .catch(error => {
      console.error('Error fetching participants:', error);
      throw error;
    });
}
