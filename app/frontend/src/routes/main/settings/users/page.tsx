import { toast } from "sonner";
import { UserTable } from "./user-table";
import { listUsers } from "@/lib/api/adminApi";
import { AdminGuard } from "@/components/auth/admin-guard";
import { SettingsHeader } from "@/components/settings/settings-header";
import { SettingsSkeleton } from "@/components/settings/settings-skeleton";
import { useSettingsData } from "@/components/settings/use-settings-data";

function UserList() {
  const [users, setUsers] = useSettingsData("users", listUsers, (error) => {
    console.error("Failed to fetch users:", error);
    toast.error("Failed to load the users");
  });

  if (users === null) return <SettingsSkeleton rows={4} />;
  if (users.length === 0) return <div className="py-6 text-center text-muted-foreground">No users found</div>;
  return <UserTable users={users} onChange={(update) => setUsers((current) => update(current ?? []))} />;
}

export default function UsersPage() {
  return (
    <AdminGuard>
      <SettingsHeader title="Users" description="Approve new users and change their roles." />
      <UserList />
    </AdminGuard>
  );
}
