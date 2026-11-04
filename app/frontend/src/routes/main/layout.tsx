import { Suspense, useLayoutEffect, useState, type ReactNode } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { AppHeader } from "@/components/header/app-header";
import { AuthGuard } from "@/components/auth/auth-guard";
import { Spinner } from "@/components/ui/spinner";
import { inPageTransition, pageCommitted, pageKey } from "@/lib/page-transition";
import { cn } from "@/lib/utils";

export default function Layout() {
  const { pathname } = useLocation();
  // The new page is in the DOM: a page transition waiting for it goes ahead (see lib/page-transition.tsx).
  useLayoutEffect(() => {
    pageCommitted(pathname);
  }, [pathname]);

  return (
    <AuthGuard>
      <div className="h-full overflow-hidden">
        <AppHeader />
        <main className="pt-14 h-full overflow-hidden flex flex-col">
          {/* Switching between the reports of a project (the same page) keeps the page. */}
          <Page key={pageKey(pathname)}>
            {/* The pages are lazy chunks: while one loads the header stays (the router's own fallback would replace it). */}
            <Suspense
              fallback={
                <div className="flex flex-1 items-center justify-center">
                  <Spinner className="h-6 w-6" />
                </div>
              }
            >
              <Outlet />
            </Suspense>
          </Page>
        </main>
      </div>
    </AuthGuard>
  );
}

// A new page fades in, unless a page transition brings it in (which moves it instead, as `data-page`). Decided once, as it mounts: a
// fade that only started when the transition ends would flash the page. Only its opacity changes: a page that slid
// in by itself would move its sticky bars and its skeleton with it.
function Page({ children }: { children: ReactNode }) {
  const [fadeIn] = useState(() => !inPageTransition());
  return (
    <div
      data-page
      className={cn(
        "flex min-h-0 flex-1 flex-col",
        fadeIn && "motion-safe:animate-in motion-safe:fade-in motion-safe:duration-200 motion-safe:ease-out"
      )}
    >
      {children}
    </div>
  );
}
