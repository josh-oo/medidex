import apiClient from "./apiClient";
import { AxiosRequestConfig } from "axios";

export const listApiKeys = (config?: AxiosRequestConfig): Promise<string[]> => {
  return apiClient.get<string[]>("/users/me/api_keys", config).then((response) => response.data);
};

export const createApiKey = (config?: AxiosRequestConfig): Promise<string> => {
  return apiClient
    .put<{ api_key: string }>("/users/me/api_keys", {}, config)
    .then((response) => response.data.api_key);
};

export const deleteApiKey = (keyId: string, config?: AxiosRequestConfig): Promise<void> => {
  return apiClient.delete(`/users/me/api_keys/${keyId}`, config).then(() => undefined);
};
