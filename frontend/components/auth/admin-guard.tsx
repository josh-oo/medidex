"use client";

import { useAuthStore } from "@/hooks/use-auth";
import { Spinner } from "@/components/ui/spinner";

// Nested inside AuthGuard, which already guarantees an authenticated,
// approved user by the time this renders. This only gates the UI - the
// backend independently enforces the ADMIN role on every admin endpoint.
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const status = useAuthStore((s) => s.status);
  const user = useAuthStore((s) => s.user);

  if (status !== "authenticated") {
    return (
      <div className="flex h-full w-full items-center justify-center">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  if (!user?.isAdmin) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-6 text-center">
        <h2 className="text-lg font-semibold">Access denied</h2>
        <p className="text-sm text-muted-foreground">You need admin access to view this page.</p>
      </div>
    );
  }

  return <>{children}</>;
}
