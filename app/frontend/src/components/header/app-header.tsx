import { Users, KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HeaderUser } from "./header-user";
import { Link, useLocation } from "react-router-dom";
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
    <header className="bg-background fixed left-0 right-0 top-0 z-50 flex w-full items-center border-b h-14">
      <div className="flex h-full w-full items-center justify-between px-4">
        {/* Left side - Logo */}
        <div className="flex items-center">
          <Link to="/" className="flex cursor-pointer select-none items-center">
            <img
              src="/images/logo.svg"
              alt="Medidex"
              width={100}
              height={40}
              className="h-8 w-auto select-none"
              draggable={false}
            />
          </Link>
        </div>

        {/* Right side - Navigation and User */}
        <div className="flex items-center gap-1">
          {/* Navigation buttons */}
          <nav className="flex items-center gap-1 mr-2">
            {user && (
              <Button
                variant={pathname === "/settings/api-keys" ? "secondary" : "ghost"}
                size="sm"
                asChild
                className={cn(
                  "gap-2",
                  pathname === "/settings/api-keys" && "bg-secondary"
                )}
              >
                <Link to="/settings/api-keys">
                  <KeyRound className="h-4 w-4" />
                  <span className="hidden sm:inline">API Keys</span>
                </Link>
              </Button>
            )}
            {isAdmin && (
              <Button
                variant={pathname === "/user-management" ? "secondary" : "ghost"}
                size="sm"
                asChild
                className={cn(
                  "gap-2",
                  pathname === "/user-management" && "bg-secondary"
                )}
              >
                <Link to="/user-management">
                  <Users className="h-4 w-4" />
                  <span className="hidden sm:inline">Users</span>
                </Link>
              </Button>
            )}
          </nav>

          {/* User dropdown */}
          {user && <HeaderUser user={user} />}
        </div>
      </div>
    </header>
  );
}
