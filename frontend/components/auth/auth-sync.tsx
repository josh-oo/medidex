"use client";

import { useEffect } from "react";
import { getKeycloak, initKeycloak } from "@/lib/client/keycloak";
import { syncSession } from "@/lib/client/syncSession";

// Adopts the tokens the server already has (from the httpOnly cookies) into
// the browser's keycloak-js instance, with no redirect or iframe involved,
// then keeps both in sync: keycloak-js refreshes the access token before it
// expires, and every time it does, the new tokens are mirrored back into the
// httpOnly cookies so server-rendered pages and the /api/backend/* proxy
// routes keep seeing a valid one.
export function AuthSync({
  accessToken,
  refreshToken,
  idToken,
}: {
  accessToken: string;
  refreshToken?: string;
  idToken?: string;
}) {
  useEffect(() => {
    const keycloak = getKeycloak();
    let cancelled = false;

    const trySync = async () => {
      try {
        const refreshed = await keycloak.updateToken(60);
        if (refreshed) {
          await syncSession(keycloak);
        }
      } catch {
        // Refresh token has also expired; the next server request will
        // bounce through middleware to /login, which re-establishes it.
      }
    };

    initKeycloak({
      token: accessToken,
      refreshToken,
      idToken,
      checkLoginIframe: false,
    })
      .then(() => {
        if (!cancelled) return trySync();
      })
      .catch((error) => console.error("Keycloak session adoption failed", error));

    const interval = setInterval(trySync, 20_000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [accessToken, refreshToken, idToken]);

  return null;
}
