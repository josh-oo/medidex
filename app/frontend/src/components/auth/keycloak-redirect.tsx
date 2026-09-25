import { useEffect, useRef } from "react";
import { getKeycloak, initKeycloak } from "@/lib/client/keycloak";

export function KeycloakRedirect({ action }: { action: "login" | "register" }) {
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const keycloak = getKeycloak();

    initKeycloak({ pkceMethod: "S256", checkLoginIframe: false })
      .then(async (authenticated) => {
        if (authenticated) {
          window.location.href = "/";
          return;
        }

        const redirectUri = `${window.location.origin}/${action}`;
        if (action === "register") {
          await keycloak.register({ redirectUri });
        } else {
          await keycloak.login({ redirectUri });
        }
      })
      .catch((error) => {
        console.error("Keycloak redirect failed", error);
      });
  }, [action]);

  return (
    <div className="bg-muted flex min-h-svh flex-col items-center justify-center gap-4 p-6 md:p-10">
      <p className="text-muted-foreground">
        {action === "register" ? "Redirecting you to create an account…" : "Redirecting you to sign in…"}
      </p>
    </div>
  );
}
