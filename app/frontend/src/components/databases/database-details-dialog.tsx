import { useEffect, useState, type FormEvent } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getUserNamesByIds } from "@/lib/api/adminApi";
import { updateDatabase } from "@/lib/api/databaseApi";
import { useAuthStore } from "@/hooks/use-auth";
import { refreshStudyDatabases, type StudyDatabase } from "@/lib/databases";
import type { EligibilityCriterion } from "@/types/apiDTOs";
import { EligibilityCriteriaEditor, EligibilityCriteriaList, criteriaComplete, trimCriteria } from "./eligibility-criteria";

interface DatabaseDetailsDialogProps {
  database: StudyDatabase;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Its owner can edit the name, the description and the eligibility criteria. */
  canEdit: boolean;
  /** Opens straight into editing (its owner only). */
  editing?: boolean;
}

/** The name, description, owner and eligibility criteria of a database; its owner edits them here. */
export function DatabaseDetailsDialog({
  database,
  open,
  onOpenChange,
  canEdit,
  editing: startEditing = false,
}: DatabaseDetailsDialogProps) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [eligibilityCriteria, setEligibilityCriteria] = useState<EligibilityCriterion[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [ownerName, setOwnerName] = useState<string | null>(null);
  const userId = useAuthStore((s) => s.user?.id);

  useEffect(() => {
    if (!open || !database.owner) {
      setOwnerName(null);
      return;
    }
    if (database.owner === userId) {
      setOwnerName("You");
      return;
    }
    getUserNamesByIds([database.owner])
      .then((names) => setOwnerName(names.get(database.owner!) ?? null))
      .catch(() => setOwnerName(null));
  }, [open, database.owner, userId]);

  const startEdit = () => {
    setName(database.name);
    setDescription(database.description ?? "");
    setEligibilityCriteria(database.eligibilityCriteria);
    setError(null);
    setEditing(true);
  };

  // Every opening starts from what the database holds now.
  useEffect(() => {
    if (!open) return;
    if (canEdit && startEditing) startEdit();
    else setEditing(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const canSave = name.trim().length > 0 && criteriaComplete(eligibilityCriteria) && !saving;

  const handleSave = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await updateDatabase(database.id, {
        name: name.trim(),
        description: description.trim(),
        eligibilityCriteria: trimCriteria(eligibilityCriteria),
      });
      await refreshStudyDatabases();
      toast.success(`Database "${name.trim()}" saved`);
      setEditing(false);
    } catch (saveError) {
      const detail = axios.isAxiosError(saveError) ? saveError.response?.data?.detail : null;
      setError(typeof detail === "string" ? detail : "The database could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => !saving && onOpenChange(nextOpen)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
        {editing ? (
          <form onSubmit={handleSave} className="space-y-4">
            <DialogHeader>
              <DialogTitle>Edit database</DialogTitle>
              <DialogDescription>
                What the database is called, what it collects and which studies belong in it.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="edit-database-name">Name</Label>
              <Input id="edit-database-name" value={name} onChange={(event) => setName(event.target.value)} autoFocus />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-database-description">Description</Label>
              <Textarea
                id="edit-database-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="What it collects (optional)"
                rows={2}
              />
            </div>
            <div className="space-y-2">
              <Label id="edit-database-criteria-label">Eligibility criteria</Label>
              <div role="group" aria-labelledby="edit-database-criteria-label">
                <EligibilityCriteriaEditor criteria={eligibilityCriteria} onChange={setEligibilityCriteria} />
              </div>
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                disabled={saving}
                onClick={() => (startEditing ? onOpenChange(false) : setEditing(false))}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={!canSave}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <div className="space-y-4">
            <DialogHeader>
              <DialogTitle>{database.name}</DialogTitle>
              <DialogDescription>{database.description ?? "Which studies belong in this database."}</DialogDescription>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              Owner: <span className="font-medium text-foreground">{database.owner ? ownerName ?? "unknown" : "nobody"}</span>
            </p>
            <section aria-labelledby="database-criteria-heading" className="space-y-2">
              <h3 id="database-criteria-heading" className="text-sm font-medium">
                Eligibility criteria
              </h3>
              <div className="max-h-[50vh] overflow-auto">
                <EligibilityCriteriaList criteria={database.eligibilityCriteria} />
              </div>
            </section>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Close
              </Button>
              {canEdit && (
                <Button type="button" variant="outline" className="gap-2" onClick={startEdit}>
                  <Pencil className="h-4 w-4" />
                  Edit
                </Button>
              )}
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
