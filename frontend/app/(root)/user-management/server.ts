"use server";

import { adminGuard } from "../../../guards/role.guard";
import { UpdateUserDto } from "../../../types/user/update-user.dto";
import { UserDto } from "../../../types/user/user.dto";
import * as keycloakAdmin from "../../../lib/server/keycloakAdmin";

export async function getUsers(): Promise<UserDto[]> {
  await adminGuard();
  return keycloakAdmin.listUsers();
}

export async function getUserById(id: string): Promise<UserDto | null> {
  return keycloakAdmin.getUserById(id);
}

export async function updateUser(
  id: string,
  updateUserDto: UpdateUserDto
): Promise<UserDto> {
  await adminGuard();
  await keycloakAdmin.updateUserRoles(id, updateUserDto.roles);
  const user = await keycloakAdmin.getUserById(id);
  if (!user) {
    throw new Error("User not found after update");
  }
  return user;
}

export async function deleteUser(id: string): Promise<void> {
  await adminGuard();
  await keycloakAdmin.deleteUser(id);
}
