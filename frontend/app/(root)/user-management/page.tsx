import { UserTable } from "./user-table";
import { getUsers } from "./server";
import { UserDto } from "../../../types/user/user.dto";
import { adminGuard } from "../../../guards/role.guard";

export default async function UserManagementPage() {
  await adminGuard();
  const users: UserDto[] = await getUsers();

  return (
    <div className="p-4 md:px-8 md:py-6">
      <h1 className="text-2xl font-bold">User Management</h1>
      <p className="text-sm text-gray-500">
        Welcome to the user management page
      </p>
      <div className="mt-4"></div>
      {users.length > 0 ? (
        <UserTable initialUsers={users} />
      ) : (
        <div className="text-center text-gray-500 py-6">No users found</div>
      )}
    </div>
  );
}
