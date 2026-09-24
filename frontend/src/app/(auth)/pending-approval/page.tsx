import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Clock } from "lucide-react";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { getKeycloak, initKeycloak } from "@/lib/client/keycloak";

export default function PendingApprovalPage() {
  const navigate = useNavigate();

  useEffect(() => {
    // Poll for approval; forcing a token refresh (updateToken(-1) always
    // refreshes) so a newly granted role takes effect immediately instead of
    // waiting for the current token to expire naturally.
    const checkApproval = async () => {
      try {
        const authenticated = await initKeycloak({
          onLoad: "check-sso",
          checkLoginIframe: false,
          silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
        });
        if (!authenticated) return;

        await getKeycloak().updateToken(-1);
        const roles: string[] = (getKeycloak().tokenParsed as { roles?: string[] } | undefined)?.roles ?? [];

        if (roles.includes("APPROVED")) {
          navigate("/");
        }
      } catch (error) {
        // Ignore transient errors, try again on the next tick.
      }
    };

    // Check every 3 seconds
    const interval = setInterval(() => {
      void checkApproval();
    }, 3000);

    return () => clearInterval(interval);
  }, [navigate]);

  return (
    <div className="bg-muted flex min-h-svh flex-col items-center justify-center p-6 md:p-10">
      <div className="w-full max-w-md">
        <Card>
          <CardHeader className="text-center">
            <div className="flex justify-center mb-4">
              <Clock className="h-16 w-16 text-muted-foreground" />
            </div>
            <CardTitle className="text-2xl">Account Pending Approval</CardTitle>
            <CardDescription>
              Your account has been created successfully
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center space-y-4">
            <p className="text-sm text-muted-foreground">
              An administrator needs to approve your account before you can access the platform.
              Once approved, you'll be redirected to the login page automatically.
            </p>
            <p className="text-sm text-muted-foreground">
              If you have any questions, please contact your system administrator.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}