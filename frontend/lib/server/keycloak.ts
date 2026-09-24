import { NextResponse } from "next/server";

const KEYCLOAK_REALM = process.env.KEYCLOAK_REALM!;
const KEYCLOAK_CLIENT_ID = process.env.KEYCLOAK_CLIENT_ID!;

// Server-to-server calls (the refresh fallback below) go over the compose
// network directly, not through the browser-facing hostname.
const internalRealmUrl = `${process.env.KEYCLOAK_INTERNAL_URL}/realms/${KEYCLOAK_REALM}`;
const keycloakTokenUrl = `${internalRealmUrl}/protocol/openid-connect/token`;

export const ACCESS_TOKEN_COOKIE = "kc_access_token";
export const REFRESH_TOKEN_COOKIE = "kc_refresh_token";
export const ID_TOKEN_COOKIE = "kc_id_token";

export interface AccessTokenPayload {
  sub: string;
  email?: string;
  name?: string;
  preferred_username?: string;
  roles?: string[];
  exp: number;
}

export function decodeToken(token: string): AccessTokenPayload | null {
  try {
    const payload = token.split(".")[1];
    return JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
  } catch {
    return null;
  }
}

export interface KeycloakTokens {
  access_token: string;
  refresh_token?: string;
  id_token?: string;
}

// The frontend is a public client (no secret) - keycloak-js in the browser
// drives the actual login/PKCE/refresh flow directly against Keycloak. This
// is only a fallback for requests that reach the server before client JS has
// run (a hard reload, a deep link with a stale cookie), so middleware can
// self-heal an expiring access token from the refresh token cookie alone.
export async function refreshTokens(refreshToken: string): Promise<KeycloakTokens> {
  const response = await fetch(keycloakTokenUrl, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: KEYCLOAK_CLIENT_ID,
      refresh_token: refreshToken,
    }),
  });
  if (!response.ok) {
    throw new Error(`Keycloak token refresh failed: ${response.status} ${await response.text()}`);
  }
  return response.json();
}

function maxAgeFor(token: string): number {
  const payload = decodeToken(token);
  if (!payload?.exp) return 0;
  return Math.max(payload.exp - Math.floor(Date.now() / 1000), 0);
}

export function applyTokenCookies(res: NextResponse, tokens: KeycloakTokens) {
  const base = {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax" as const,
    path: "/",
  };
  res.cookies.set(ACCESS_TOKEN_COOKIE, tokens.access_token, {
    ...base,
    maxAge: maxAgeFor(tokens.access_token),
  });
  if (tokens.refresh_token) {
    res.cookies.set(REFRESH_TOKEN_COOKIE, tokens.refresh_token, {
      ...base,
      maxAge: maxAgeFor(tokens.refresh_token),
    });
  }
  if (tokens.id_token) {
    res.cookies.set(ID_TOKEN_COOKIE, tokens.id_token, {
      ...base,
      maxAge: maxAgeFor(tokens.refresh_token ?? tokens.id_token),
    });
  }
}

export function clearSessionCookies(res: NextResponse) {
  for (const name of [ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE, ID_TOKEN_COOKIE]) {
    res.cookies.set(name, "", { path: "/", maxAge: 0 });
  }
}
