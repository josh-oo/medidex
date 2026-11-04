import Keycloak, { type KeycloakInitOptions } from "keycloak-js";

let instance: Keycloak | null = null;
let initPromise: Promise<boolean> | null = null;

export function getKeycloak(): Keycloak {
  if (!instance) {
    instance = new Keycloak({
      url: import.meta.env.VITE_KEYCLOAK_URL!,
      realm: import.meta.env.VITE_KEYCLOAK_REALM!,
      clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID!,
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
// there's no session or the refresh token itself has expired. `fresh` always
// refreshes, for a request that takes long to reach the backend (a large
// upload a proxy buffers before passing it on): its token lives as long as
// tokens do.
export async function getAccessToken(fresh = false): Promise<string | null> {
  const keycloak = getKeycloak();
  if (!keycloak.authenticated) return null;
  try {
    await keycloak.updateToken(fresh ? -1 : 30);
  } catch {
    return null;
  }
  return keycloak.token ?? null;
}
