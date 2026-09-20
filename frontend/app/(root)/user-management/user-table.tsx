"use client";

import { useState } from "react";
import { UserDto } from "../../../types/user/user.dto";
import { PencilIcon, TrashIcon, CheckCircle, XCircle } from "lucide-react";
import { Button } from "../../../components/ui/button";
import { UpdateUserDialog } from "./update-user-dialog";
import { DeleteUserDialog } from "./delete-user-dialog";
import { toast } from "sonner";

interface Props {
  initialUsers: UserDto[];
}

export const UserTable: React.FC<Props> = (props) => {
  const { initialUsers } = props;
  const [users, setUsers] = useState<UserDto[]>(initialUsers);
  const [selectedUser, setSelectedUser] = useState<UserDto | null>(null);
  const [isUpdateDialogOpen, setIsUpdateDialogOpen] = useState(false);
  const [userToDelete, setUserToDelete] = useState<UserDto | null>(null);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [approvingUserId, setApprovingUserId] = useState<string | null>(null);

  const handleEditClick = (user: UserDto) => {
    setSelectedUser(user);
    setIsUpdateDialogOpen(true);
  };

  const handleDeleteClick = (user: UserDto) => {
    setUserToDelete(user);
    setIsDeleteDialogOpen(true);
  };

  const handleUserUpdated = (updatedUser: UserDto) => {
    setUsers((prev) =>
      prev.map((user) => (user.id === updatedUser.id ? updatedUser : user))
    );
  };

  const handleUserDeleted = (userId: string) => {
    setUsers((prev) => prev.filter((user) => user.id !== userId));
  };

  const handleApproveUser = async (userId: string) => {
    setApprovingUserId(userId);
    try {
      const response = await fetch(`/api/users/${userId}/approve`, {
        method: "PATCH",
      });

      if (!response.ok) {
        throw new Error("Failed to approve user");
      }

      setUsers((prev) =>
        prev.map((u) =>
          u.id === userId ? { ...u, isApproved: true } : u
        )
      );
      toast.success("User approved successfully");
    } catch (error) {
      toast.error("Failed to approve user");
      console.error(error);
    } finally {
      setApprovingUserId(null);
    }
  };

  return (
    <div className="border rounded-lg">
      <table className="w-full">
        <thead className="bg-gray-50 dark:bg-gray-800">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Name
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Email
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Role
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              Status
            </th>
            <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
          {users.map((user) => (
            <tr key={user.id}>
              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                {user.name}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                {user.email}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm">
                {user.roles.join(", ")}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-sm">
                {user.isApproved ? (
                  <span className="inline-flex items-center gap-1 text-green-600">
                    <CheckCircle className="h-4 w-4" />
                    Approved
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-yellow-600">
                    <XCircle className="h-4 w-4" />
                    Pending
                  </span>
                )}
              </td>
              <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                <div className="flex justify-end gap-2">
                  {!user.isApproved && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleApproveUser(user.id)}
                      disabled={approvingUserId === user.id}
                    >
                      {approvingUserId === user.id ? "Approving..." : "Approve"}
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleEditClick(user)}
                  >
                    <PencilIcon className="h-4 w-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDeleteClick(user)}
                  >
                    <TrashIcon className="h-4 w-4" />
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <UpdateUserDialog
        user={selectedUser}
        open={isUpdateDialogOpen}
        onOpenChange={setIsUpdateDialogOpen}
        onUserUpdated={handleUserUpdated}
      />
      <DeleteUserDialog
        user={userToDelete}
        open={isDeleteDialogOpen}
        onOpenChange={setIsDeleteDialogOpen}
        onUserDeleted={handleUserDeleted}
      />
    </div>
  );
};
