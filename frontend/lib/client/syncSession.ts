"use client";

import type Keycloak from "keycloak-js";

// Mirrors the browser-held Keycloak tokens into httpOnly cookies so
// server-side code (middleware, the /api/backend/* proxy routes) can forward
// a valid Authorization header without any client JS ever reading the raw
// token back out.
export async function syncSession(keycloak: Keycloak): Promise<void> {
  if (!keycloak.token) return;

  await fetch("/api/auth/sync", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      accessToken: keycloak.token,
      refreshToken: keycloak.refreshToken,
      idToken: keycloak.idToken,
    }),
  });
}

export async function clearSession(): Promise<void> {
  await fetch("/api/auth/sync", { method: "DELETE" });
}
