"use server";

import { Role } from "../../../enums/role.enum";
import { adminGuard } from "../../../guards/role.guard";
import prisma from "../../../lib/db";
import { UpdateUserDto } from "../../../types/user/update-user.dto";
import { UserDto } from "../../../types/user/user.dto";

export async function getUsers(): Promise<UserDto[]> {
  await adminGuard();
  const users = await prisma.user.findMany();

  return users.map((user) => ({
    id: user.id,
    name: user.name,
    email: user.email,
    roles: user.roles as Role[],
    isApproved: user.isApproved,
  }));
}

export async function getUserById(id: string): Promise<UserDto | null> {
  const user = await prisma.user.findUnique({
    where: { id },
  });

  if (!user) return null;

  return {
    id: user.id,
    name: user.name,
    email: user.email,
    roles: user.roles as Role[],
    isApproved: user.isApproved,
  };
}

export async function updateUser(
  id: string,
  updateUserDto: UpdateUserDto
): Promise<UserDto> {
  await adminGuard();
  const user = await prisma.user.update({
    where: { id },
    data: updateUserDto,
  });

  return {
    id: user.id,
    name: user.name,
    email: user.email,
    roles: user.roles as Role[],
    isApproved: user.isApproved,
  };
}

export async function deleteUser(id: string): Promise<void> {
  await adminGuard();
  await prisma.user.delete({
    where: { id },
  });
}
