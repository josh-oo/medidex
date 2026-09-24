import apiClient from "./apiClient";
import { InterventionDto } from "../../types/apiDTOs";
import { AxiosRequestConfig } from "axios";

type InterventionListEntry = {
  InterventionID: number;
  InterventionDescription: string;
};

export const getInterventions = (
  config?: AxiosRequestConfig
): Promise<InterventionDto[]> => {
  const path = `/interventions`;
  return apiClient.get<InterventionListEntry[]>(path, config)
    .then(response => {
      return response.data.map(entry => ({
        ID: entry.InterventionID,
        Description: entry.InterventionDescription,
      }));
    })
    .catch(error => {
      console.error('Error fetching interventions:', error);
      throw error;
    });
}
