import { HeaderUser } from "./header-user";
import { MedidexLogo } from "./medidex-logo";
import { PageLink } from "@/lib/page-transition";
import { useAuthStore } from "@/hooks/use-auth";

export function AppHeader() {
  const authUser = useAuthStore((s) => s.user);

  const user = authUser
    ? {
        name: authUser.name,
        email: authUser.email,
        avatar: "",
        isAdmin: authUser.isAdmin,
      }
    : null;

  return (
    <header className="bg-canvas fixed left-0 right-0 top-0 z-50 flex w-full items-center h-14 border-b border-border pt-[env(safe-area-inset-top)]">
      <div className="flex h-full w-full items-center justify-between px-4 md:px-6">
        {/* Left side - Logo */}
        <div className="flex items-center">
          <PageLink
            to="/"
            aria-label="Medidex home"
            className="flex cursor-pointer items-center rounded-md transition-opacity hover:opacity-80 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
          >
            <MedidexLogo />
          </PageLink>
        </div>

        {/* Right side - User dropdown */}
        {user && <HeaderUser user={user} />}
      </div>
    </header>
  );
}

