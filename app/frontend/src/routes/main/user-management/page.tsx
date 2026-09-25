import { useEffect, useState } from "react";
import { UserTable } from "./user-table";
import { listUsers } from "@/lib/api/adminApi";
import { UserDto } from "@/types/user/user.dto";
import { AdminGuard } from "@/components/auth/admin-guard";
import { useAuthStore } from "@/hooks/use-auth";
import { Spinner } from "@/components/ui/spinner";

export default function UserManagementPage() {
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
      <div className="p-4 md:px-8 md:py-6">
        <h1 className="text-2xl font-bold">User Management</h1>
        <p className="text-sm text-gray-500">
          Welcome to the user management page
        </p>
        <div className="mt-4"></div>
        {users === null ? (
          <div className="flex justify-center py-10">
            <Spinner className="h-6 w-6" />
          </div>
        ) : users.length > 0 ? (
          <UserTable initialUsers={users} />
        ) : (
          <div className="text-center text-gray-500 py-6">No users found</div>
        )}
      </div>
    </AdminGuard>
  );
}
