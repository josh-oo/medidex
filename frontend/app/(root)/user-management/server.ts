"use server";

import { adminGuard } from "../../../guards/role.guard";
import { UpdateUserDto } from "../../../types/user/update-user.dto";
import { UserDto } from "../../../types/user/user.dto";
import { getBackendHeaders } from "../../../lib/server/backendHeaders";
import * as adminApi from "../../../lib/api/adminApi";

export async function getUsers(): Promise<UserDto[]> {
  await adminGuard();
  return adminApi.listUsers({ headers: await getBackendHeaders() });
}

export async function getUserById(id: string): Promise<UserDto | null> {
  return adminApi.getUserById(id, { headers: await getBackendHeaders() });
}

export async function updateUser(
  id: string,
  updateUserDto: UpdateUserDto
): Promise<UserDto> {
  await adminGuard();
  return adminApi.updateUserRoles(id, updateUserDto.roles, { headers: await getBackendHeaders() });
}

export async function deleteUser(id: string): Promise<void> {
  await adminGuard();
  await adminApi.deleteUser(id, { headers: await getBackendHeaders() });
}
