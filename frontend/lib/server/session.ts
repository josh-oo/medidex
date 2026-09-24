import { cookies } from "next/headers";
import { ACCESS_TOKEN_COOKIE, ID_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE, decodeToken } from "./keycloak";

export async function getSession() {
  const store = await cookies();
  const accessToken = store.get(ACCESS_TOKEN_COOKIE)?.value;
  if (!accessToken) return null;

  const payload = decodeToken(accessToken);
  if (!payload) return null;

  const roles = payload.roles ?? [];

  return {
    accessToken,
    refreshToken: store.get(REFRESH_TOKEN_COOKIE)?.value,
    idToken: store.get(ID_TOKEN_COOKIE)?.value,
    user: {
      id: payload.sub,
      email: payload.email,
      name: payload.name ?? payload.preferred_username ?? payload.email ?? "User",
      roles,
      isAdmin: roles.includes("ADMIN"),
      isApproved: roles.includes("APPROVED"),
    },
  };
}
