import { Role } from "../../enums/role.enum";

const KEYCLOAK_INTERNAL_URL = process.env.KEYCLOAK_INTERNAL_URL!;
const KEYCLOAK_REALM = process.env.KEYCLOAK_REALM!;
const ADMIN_CLIENT_ID = process.env.KEYCLOAK_ADMIN_CLIENT_ID!;
const ADMIN_CLIENT_SECRET = process.env.KEYCLOAK_ADMIN_CLIENT_SECRET!;

const adminBaseUrl = `${KEYCLOAK_INTERNAL_URL}/admin/realms/${KEYCLOAK_REALM}`;
const tokenUrl = `${KEYCLOAK_INTERNAL_URL}/realms/${KEYCLOAK_REALM}/protocol/openid-connect/token`;

const APP_ROLE_NAMES = [Role.USER, Role.ADMIN] as const;

export interface KeycloakUserSummary {
  id: string;
  name: string;
  email: string;
  roles: Role[];
  isApproved: boolean;
}

// Cached in-memory (per server instance) since the same service-account
// client credentials are reused across every admin API call.
let cachedToken: { token: string; expiresAt: number } | null = null;

async function getAdminToken(): Promise<string> {
  if (cachedToken && Date.now() < cachedToken.expiresAt - 5_000) {
    return cachedToken.token;
  }

  const response = await fetch(tokenUrl, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "client_credentials",
      client_id: ADMIN_CLIENT_ID,
      client_secret: ADMIN_CLIENT_SECRET,
    }),
  });

  if (!response.ok) {
    throw new Error(`Failed to obtain Keycloak admin token (${response.status})`);
  }

  const data = await response.json();
  cachedToken = { token: data.access_token, expiresAt: Date.now() + data.expires_in * 1000 };
  return cachedToken.token;
}

async function adminFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await getAdminToken();
  return fetch(`${adminBaseUrl}${path}`, {
    ...init,
    headers: {
      ...(init.headers ?? {}),
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    cache: "no-store",
  });
}

// The realm's role ids rarely change, so this is cached for the life of the server.
let cachedRealmRoleIds: Record<string, string> | null = null;

async function getRealmRoleIds(): Promise<Record<string, string>> {
  if (cachedRealmRoleIds) return cachedRealmRoleIds;
  const res = await adminFetch("/roles");
  if (!res.ok) throw new Error("Failed to fetch realm roles from Keycloak");
  const roles: { id: string; name: string }[] = await res.json();
  cachedRealmRoleIds = Object.fromEntries(roles.map((r) => [r.name, r.id]));
  return cachedRealmRoleIds;
}

let cachedApprovedGroupId: string | null = null;

async function getApprovedGroupId(): Promise<string> {
  if (cachedApprovedGroupId) return cachedApprovedGroupId;
  const res = await adminFetch("/groups?search=approved-users");
  if (!res.ok) throw new Error("Failed to fetch groups from Keycloak");
  const groups: { id: string; name: string }[] = await res.json();
  const group = groups.find((g) => g.name === "approved-users");
  if (!group) throw new Error("The 'approved-users' group is missing from the Keycloak realm");
  cachedApprovedGroupId = group.id;
  return cachedApprovedGroupId;
}

async function getApprovedUserIds(): Promise<Set<string>> {
  const groupId = await getApprovedGroupId();
  const res = await adminFetch(`/groups/${groupId}/members?briefRepresentation=true&max=1000`);
  if (!res.ok) throw new Error("Failed to fetch approved-users group members from Keycloak");
  const members: { id: string }[] = await res.json();
  return new Set(members.map((m) => m.id));
}

async function getUserRoles(userId: string): Promise<Role[]> {
  const res = await adminFetch(`/users/${userId}/role-mappings/realm`);
  if (!res.ok) return [Role.USER];
  const roleReps: { name: string }[] = await res.json();
  const roles = roleReps
    .map((r) => r.name)
    .filter((name): name is Role => (APP_ROLE_NAMES as readonly string[]).includes(name));
  return roles.length ? roles : [Role.USER];
}

function displayName(user: { firstName?: string; lastName?: string; username: string }): string {
  const fullName = `${user.firstName ?? ""} ${user.lastName ?? ""}`.trim();
  return fullName || user.username;
}

export async function listUsers(): Promise<KeycloakUserSummary[]> {
  const [usersRes, approvedIds] = await Promise.all([
    adminFetch("/users?max=1000"),
    getApprovedUserIds(),
  ]);
  if (!usersRes.ok) throw new Error("Failed to fetch users from Keycloak");
  const users: { id: string; username: string; email: string; firstName?: string; lastName?: string }[] =
    await usersRes.json();

  return Promise.all(
    users.map(async (user) => ({
      id: user.id,
      name: displayName(user),
      email: user.email,
      roles: await getUserRoles(user.id),
      isApproved: approvedIds.has(user.id),
    }))
  );
}

export async function getUserNamesByIds(ids: string[]): Promise<Map<string, string>> {
  const entries = await Promise.all(
    ids.map(async (id) => {
      const res = await adminFetch(`/users/${id}`);
      if (!res.ok) return null;
      const user = await res.json();
      return [id, displayName(user)] as const;
    })
  );
  return new Map(entries.filter((entry): entry is [string, string] => entry !== null));
}

export async function getUserById(id: string): Promise<KeycloakUserSummary | null> {
  const [userRes, approvedIds] = await Promise.all([adminFetch(`/users/${id}`), getApprovedUserIds()]);
  if (!userRes.ok) return null;
  const user = await userRes.json();

  return {
    id,
    name: displayName(user),
    email: user.email,
    roles: await getUserRoles(id),
    isApproved: approvedIds.has(id),
  };
}

export async function updateUserRoles(id: string, roles: Role[]): Promise<void> {
  const roleIds = await getRealmRoleIds();
  const currentRes = await adminFetch(`/users/${id}/role-mappings/realm`);
  const currentRoles: { id: string; name: string }[] = currentRes.ok ? await currentRes.json() : [];

  const toAdd = roles
    .filter((name) => !currentRoles.some((r) => r.name === name))
    .map((name) => ({ id: roleIds[name], name }))
    .filter((role) => Boolean(role.id));

  const toRemove = currentRoles.filter(
    (r) => (APP_ROLE_NAMES as readonly string[]).includes(r.name) && !roles.includes(r.name as Role)
  );

  if (toAdd.length) {
    await adminFetch(`/users/${id}/role-mappings/realm`, { method: "POST", body: JSON.stringify(toAdd) });
  }
  if (toRemove.length) {
    await adminFetch(`/users/${id}/role-mappings/realm`, { method: "DELETE", body: JSON.stringify(toRemove) });
  }
}

export async function approveUser(id: string): Promise<void> {
  const groupId = await getApprovedGroupId();
  const res = await adminFetch(`/users/${id}/groups/${groupId}`, { method: "PUT" });
  if (!res.ok) throw new Error("Failed to approve user in Keycloak");
}

export async function deleteUser(id: string): Promise<void> {
  const res = await adminFetch(`/users/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete user in Keycloak");
}
