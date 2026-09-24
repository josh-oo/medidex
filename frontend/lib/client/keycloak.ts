"use client";

import Keycloak, { type KeycloakInitOptions } from "keycloak-js";

let instance: Keycloak | null = null;
let initPromise: Promise<boolean> | null = null;

export function getKeycloak(): Keycloak {
  if (!instance) {
    instance = new Keycloak({
      url: process.env.NEXT_PUBLIC_KEYCLOAK_URL!,
      realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM!,
      clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID!,
    });
  }
  return instance;
}

// keycloak-js only allows a single init() call per instance. Memoizing the
// promise makes repeated calls (e.g. React StrictMode's double effect
// invocation, or a later component adopting the same already-initialized
// session) idempotent instead of throwing.
export function initKeycloak(options: KeycloakInitOptions): Promise<boolean> {
  if (!initPromise) {
    initPromise = getKeycloak().init(options);
  }
  return initPromise;
}

// Returns a token guaranteed to be valid for at least 30s, refreshing first
// if needed. Every direct browser->backend request goes through this so
// callers never have to think about expiry themselves. Returns null if
// there's no session or the refresh token itself has expired.
export async function getAccessToken(): Promise<string | null> {
  const keycloak = getKeycloak();
  if (!keycloak.authenticated) return null;
  try {
    await keycloak.updateToken(30);
  } catch {
    return null;
  }
  return keycloak.token ?? null;
}
