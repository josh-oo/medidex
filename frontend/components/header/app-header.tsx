import { auth } from "@/lib/auth";
import { headers } from "next/headers";
import { Role } from "@/enums/role.enum";
import { AppHeaderClient } from "./app-header-client";

export async function AppHeader() {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  const sessionUser = session?.user;

  const roles: Role[] = sessionUser?.roles
    ? Array.isArray(sessionUser.roles)
      ? sessionUser.roles
      : [sessionUser.roles]
    : [];

  const user = sessionUser
    ? {
        name: sessionUser.name || "User",
        email: sessionUser.email || "",
        avatar: sessionUser.image || "",
        roles,
      }
    : null;

  return <AppHeaderClient user={user} />;
}

