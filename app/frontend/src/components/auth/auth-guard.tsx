import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/hooks/use-auth";
import { Spinner } from "@/components/ui/spinner";

// Client-side replacement for the old middleware.ts: redirects to /login if
// there's no session, or to /pending-approval if the account isn't approved
// yet. Actual enforcement still lives in the backend, which independently
// verifies every request's token - this only keeps the UI from flashing
// protected content at someone who shouldn't see it.
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const status = useAuthStore((s) => s.status);
  const user = useAuthStore((s) => s.user);
  const init = useAuthStore((s) => s.init);

  useEffect(() => {
    init();
  }, [init]);

  useEffect(() => {
    if (status === "unauthenticated") {
      navigate("/login", { replace: true });
    } else if (status === "authenticated" && user && !user.isApproved) {
      navigate("/pending-approval", { replace: true });
    }
  }, [status, user, navigate]);

  if (status !== "authenticated" || !user?.isApproved) {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  return <>{children}</>;
}
