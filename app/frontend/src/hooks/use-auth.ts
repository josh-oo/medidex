import { create } from "zustand";
import type Keycloak from "keycloak-js";
import { getKeycloak, initKeycloak } from "@/lib/client/keycloak";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  roles: string[];
  isAdmin: boolean;
  isApproved: boolean;
}

interface AuthState {
  status: "initializing" | "authenticated" | "unauthenticated";
  user: AuthUser | null;
  init: () => void;
}

function userFromKeycloak(keycloak: Keycloak): AuthUser | null {
  const token = keycloak.tokenParsed as
    | { sub?: string; email?: string; name?: string; preferred_username?: string; roles?: string[] }
    | undefined;
  if (!keycloak.authenticated || !token?.sub) return null;

  const roles = token.roles ?? [];
  return {
    id: token.sub,
    email: token.email ?? "",
    name: token.name ?? token.preferred_username ?? token.email ?? "User",
    roles,
    isAdmin: roles.includes("ADMIN"),
    isApproved: roles.includes("APPROVED"),
  };
}

let initStarted = false;

export const useAuthStore = create<AuthState>((set) => ({
  status: "initializing",
  user: null,

  // Silently checks for an existing Keycloak SSO session (via a hidden
  // iframe against silent-check-sso.html) so a hard reload of a protected
  // page doesn't force a visible redirect through Keycloak's login page -
  // this is the SPA replacement for what middleware used to do server-side
  // with the httpOnly refresh-token cookie.
  init: () => {
    if (initStarted) return;
    initStarted = true;

    const keycloak = getKeycloak();
    const applyState = () => {
      const user = userFromKeycloak(keycloak);
      set({ status: user ? "authenticated" : "unauthenticated", user });
    };

    keycloak.onAuthSuccess = applyState;
    keycloak.onAuthRefreshSuccess = applyState;
    keycloak.onAuthLogout = applyState;
    keycloak.onAuthRefreshError = () => set({ status: "unauthenticated", user: null });
    keycloak.onTokenExpired = () => {
      keycloak.updateToken(30).catch(() => set({ status: "unauthenticated", user: null }));
    };

    initKeycloak({
      onLoad: "check-sso",
      pkceMethod: "S256",
      checkLoginIframe: false,
      silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
    })
      .catch((error) => console.error("Keycloak silent SSO check failed", error))
      .finally(applyState);
  },
}));
