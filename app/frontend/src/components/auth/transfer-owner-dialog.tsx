import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { useAuthStore } from "@/hooks/use-auth";
import { listApprovedUsers } from "@/lib/api/adminApi";
import type { UserDto } from "@/types/user/user.dto";

interface TransferOwnerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The name of the study database. */
  name: string;
  /** Transfers the ownership to the user; rejects to keep the dialog open. */
  onTransfer: (ownerId: string) => Promise<void>;
}

function errorDetail(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : null;
}

/** Transfers the ownership of a study database to another approved user. */
export function TransferOwnerDialog({ open, onOpenChange, name, onTransfer }: TransferOwnerDialogProps) {
  const userId = useAuthStore((s) => s.user?.id);
  const [candidates, setCandidates] = useState<UserDto[] | null>(null);
  const [ownerId, setOwnerId] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    setOwnerId("");
    setCandidates(null);
    listApprovedUsers()
      .then((users) => setCandidates(users.filter((user) => user.id !== userId)))
      .catch((error) => {
        console.error("Failed to fetch users:", error);
        setCandidates([]);
      });
  }, [open, userId]);

  const handleTransfer = async () => {
    if (!ownerId) return;
    setIsSaving(true);
    try {
      await onTransfer(ownerId);
      toast.success(`Transferred the ownership of ${name}`);
      onOpenChange(false);
    } catch (error) {
      toast.error(errorDetail(error) ?? "Failed to transfer the ownership");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpenUnlessSaving(isSaving, onOpenChange)}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Transfer database ownership</DialogTitle>
          <DialogDescription>
            Choose the new owner of <span className="font-medium text-foreground">{name}</span>. You cannot undo this
            yourself.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label htmlFor="transfer-owner">New owner</Label>
          {candidates === null ? (
            <div className="flex justify-center py-2">
              <Spinner className="h-5 w-5" />
            </div>
          ) : candidates.length === 0 ? (
            <p className="text-sm text-muted-foreground">There is no other approved user.</p>
          ) : (
            <Select value={ownerId} onValueChange={setOwnerId}>
              <SelectTrigger id="transfer-owner" className="w-full">
                <SelectValue placeholder="Choose a user" />
              </SelectTrigger>
              <SelectContent>
                {candidates.map((user) => (
                  <SelectItem key={user.id} value={user.id}>
                    {user.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
            Cancel
          </Button>
          <Button onClick={handleTransfer} disabled={!ownerId || isSaving}>
            {isSaving ? "Transferring..." : "Transfer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const setOpenUnlessSaving = (isSaving: boolean, onOpenChange: (open: boolean) => void) => (open: boolean) => {
  if (!isSaving) onOpenChange(open);
};
