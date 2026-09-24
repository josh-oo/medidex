import apiClient from "./apiClient";
import { AxiosRequestConfig } from "axios";
import { Role } from "../../enums/role.enum";
import { UserDto } from "../../types/user/user.dto";

// Wire shape returned by the backend's admin API (backend/logic/src/api/admin.py),
// which is the only thing in this app allowed to call the Keycloak Admin REST API.
interface UserSummaryResponse {
  id: string;
  name: string;
  email: string;
  roles: Role[];
  is_approved: boolean;
}

function toUserDto(user: UserSummaryResponse): UserDto {
  return {
    id: user.id,
    name: user.name,
    email: user.email,
    roles: user.roles,
    isApproved: user.is_approved,
  };
}

export const listUsers = (config?: AxiosRequestConfig): Promise<UserDto[]> => {
  return apiClient
    .get<UserSummaryResponse[]>("/admin/users", config)
    .then((response) => response.data.map(toUserDto));
};

export const getUserById = (id: string, config?: AxiosRequestConfig): Promise<UserDto | null> => {
  return apiClient
    .get<UserSummaryResponse>(`/admin/users/${id}`, config)
    .then((response) => toUserDto(response.data))
    .catch((error) => {
      if (error?.response?.status === 404) return null;
      throw error;
    });
};

export const updateUserRoles = (
  id: string,
  roles: Role[],
  config?: AxiosRequestConfig
): Promise<UserDto> => {
  return apiClient
    .put<UserSummaryResponse>(`/admin/users/${id}/roles`, { roles }, config)
    .then((response) => toUserDto(response.data));
};

export const approveUser = (id: string, config?: AxiosRequestConfig): Promise<UserDto> => {
  return apiClient
    .put<UserSummaryResponse>(`/admin/users/${id}/approve`, {}, config)
    .then((response) => toUserDto(response.data));
};

export const deleteUser = (id: string, config?: AxiosRequestConfig): Promise<void> => {
  return apiClient.delete(`/admin/users/${id}`, config).then(() => undefined);
};

export const getUserNamesByIds = async (
  ids: string[],
  config?: AxiosRequestConfig
): Promise<Map<string, string>> => {
  if (ids.length === 0) return new Map();
  const response = await apiClient.get<Record<string, string>>("/admin/users/names", {
    ...config,
    params: { ...(config?.params ?? {}), ids: ids.join(",") },
  });
  return new Map(Object.entries(response.data));
};
