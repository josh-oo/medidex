import { useEffect, useState } from "react";
import { UserTable } from "./user-table";
import { listUsers } from "@/lib/api/adminApi";
import { UserDto } from "@/types/user/user.dto";
import { AdminGuard } from "@/components/auth/admin-guard";
import { SettingsHeader } from "@/components/settings/settings-header";
import { useAuthStore } from "@/hooks/use-auth";
import { Spinner } from "@/components/ui/spinner";

export default function UsersPage() {
  const isAdmin = useAuthStore((s) => s.user?.isAdmin ?? false);
  const [users, setUsers] = useState<UserDto[] | null>(null);

  useEffect(() => {
    if (!isAdmin) return;

    listUsers()
      .then(setUsers)
      .catch((error) => {
        console.error("Failed to fetch users:", error);
        setUsers([]);
      });
  }, [isAdmin]);

  return (
    <AdminGuard>
      <SettingsHeader title="Users" description="Approve new users and change their roles." />
      {users === null ? (
        <div className="flex justify-center py-10">
          <Spinner className="h-6 w-6" />
        </div>
      ) : users.length > 0 ? (
        <UserTable initialUsers={users} />
      ) : (
        <div className="py-6 text-center text-muted-foreground">No users found</div>
      )}
    </AdminGuard>
  );
}
