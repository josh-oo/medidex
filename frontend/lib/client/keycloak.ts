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
