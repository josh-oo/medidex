"use client";

import { Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { HeaderUser } from "./header-user";
import { Role } from "@/enums/role.enum";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

interface AppHeaderClientProps {
  user: {
    name: string;
    email: string;
    avatar: string;
    roles: Role[];
  } | null;
}

export function AppHeaderClient({ user }: AppHeaderClientProps) {
  const pathname = usePathname();
  const isAdmin = user?.roles.includes(Role.ADMIN);

  return (
    <header className="bg-background fixed left-0 right-0 top-0 z-50 flex w-full items-center border-b h-14">
      <div className="flex h-full w-full items-center justify-between px-4">
        {/* Left side - Logo */}
        <div className="flex items-center">
          <Link href="/" className="flex cursor-pointer select-none items-center">
            <Image
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
                <Link href="/user-management">
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

