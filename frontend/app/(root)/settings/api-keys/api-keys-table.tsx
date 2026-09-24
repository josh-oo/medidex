"use client";

import { useState } from "react";
import { TrashIcon, Copy } from "lucide-react";
import { Button } from "../../../../components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../../../../components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../../../components/ui/dialog";
import { toast } from "sonner";
import { createApiKey, deleteApiKey } from "@/lib/api/apiKeysApi";

interface Props {
  initialApiKeys: string[];
}

function copyToClipboard(value: string) {
  navigator.clipboard.writeText(value);
  toast.success("Copied to clipboard");
}

export const ApiKeysTable: React.FC<Props> = ({ initialApiKeys }) => {
  const [apiKeys, setApiKeys] = useState<string[]>(initialApiKeys);
  const [isCreating, setIsCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [keyToDelete, setKeyToDelete] = useState<string | null>(null);

  const handleCreate = async () => {
    setIsCreating(true);
    try {
      const apiKey = await createApiKey();
      const [clientId] = apiKey.split(".");
      setApiKeys((prev) => [...prev, clientId]);
      setCreatedKey(apiKey);
    } catch (error) {
      console.error("Error creating API key:", error);
      toast.error("Failed to create API key");
    } finally {
      setIsCreating(false);
    }
  };

  const handleDelete = async () => {
    if (!keyToDelete) return;
    try {
      await deleteApiKey(keyToDelete);
      setApiKeys((prev) => prev.filter((id) => id !== keyToDelete));
      toast.success("API key deleted");
    } catch (error) {
      console.error("Error deleting API key:", error);
      toast.error("Failed to delete API key");
    } finally {
      setKeyToDelete(null);
    }
  };

  return (
    <div>
      <div className="flex justify-end mb-4">
        <Button onClick={handleCreate} disabled={isCreating}>
          {isCreating ? "Creating..." : "Create API key"}
        </Button>
      </div>

      <div className="border rounded-lg">
        <table className="w-full">
          <thead className="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Key ID
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
            {apiKeys.map((clientId) => (
              <tr key={clientId}>
                <td className="px-6 py-4 whitespace-nowrap text-sm font-mono">{clientId}</td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                  <Button variant="ghost" size="icon" onClick={() => setKeyToDelete(clientId)}>
                    <TrashIcon className="h-4 w-4" />
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {apiKeys.length === 0 && (
          <div className="text-center text-gray-500 py-6">No API keys yet</div>
        )}
      </div>

      <Dialog open={createdKey !== null} onOpenChange={(open) => !open && setCreatedKey(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>API key created</DialogTitle>
            <DialogDescription>
              This is the only time the full key is shown. Store it somewhere safe.
            </DialogDescription>
          </DialogHeader>
          {createdKey && (
            <div className="space-y-3">
              <div className="flex items-center gap-2">
                <code className="flex-1 rounded bg-gray-100 dark:bg-gray-800 px-2 py-1 text-sm break-all">
                  {createdKey}
                </code>
                <Button variant="ghost" size="icon" onClick={() => copyToClipboard(createdKey)}>
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <p className="text-xs text-gray-500">
                Send it as an <code>X-API-Key</code> header on requests to the backend, the same way
                as before.
              </p>
            </div>
          )}
          <DialogFooter>
            <Button onClick={() => setCreatedKey(null)}>Done</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={keyToDelete !== null} onOpenChange={(open) => !open && setKeyToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this API key?</AlertDialogTitle>
            <AlertDialogDescription>
              Any script using <strong>{keyToDelete}</strong> will stop being able to authenticate.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
