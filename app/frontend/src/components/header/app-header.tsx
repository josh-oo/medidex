import { Users, type LucideIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HeaderUser } from "./header-user";
import { Link, useLocation } from "react-router-dom";
import { PageLink } from "@/lib/page-transition";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/hooks/use-auth";

export function AppHeader() {
  const { pathname } = useLocation();
  const authUser = useAuthStore((s) => s.user);

  const user = authUser
    ? {
        name: authUser.name,
        email: authUser.email,
        avatar: "",
        isAdmin: authUser.isAdmin,
      }
    : null;
  const isAdmin = user?.isAdmin;

  return (
    <header className="bg-canvas fixed left-0 right-0 top-0 z-50 flex w-full items-center h-14 pt-[env(safe-area-inset-top)]">
      <div className="flex h-full w-full items-center justify-between px-4">
        {/* Left side - Logo */}
        <div className="flex items-center">
          <PageLink to="/" className="flex cursor-pointer select-none items-center">
            <img
              src="/images/logo.svg"
              alt="Medidex"
              width={100}
              height={40}
              className="h-8 w-auto select-none"
              draggable={false}
            />
          </PageLink>
        </div>

        {/* Right side - Navigation and User */}
        <div className="flex items-center gap-1">
          {/* Navigation buttons */}
          <nav className="flex items-center gap-1 mr-2">
            {isAdmin && (
              <NavLink to="/user-management" icon={Users} label="Users" active={pathname === "/user-management"} />
            )}
          </nav>

          {/* User dropdown */}
          {user && <HeaderUser user={user} />}
        </div>
      </div>
    </header>
  );
}

function NavLink({ to, icon: Icon, label, active }: { to: string; icon: LucideIcon; label: string; active: boolean }) {
  return (
    <Button variant={active ? "secondary" : "ghost"} size="sm" asChild className={cn("gap-2", active && "bg-secondary")}>
      <Link to={to} aria-current={active ? "page" : undefined}>
        <Icon className="h-4 w-4" />
        <span className="hidden sm:inline">{label}</span>
      </Link>
    </Button>
  );
}
