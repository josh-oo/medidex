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
import { updateDatabase } from "@/lib/api/databaseApi";
import { refreshStudyDatabases, type StudyDatabase } from "@/lib/databases";

interface DatabaseDetailsDialogProps {
  database: StudyDatabase;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Admins can edit the name, the description and the eligibility criteria. */
  canEdit: boolean;
  /** Opens straight into editing (admins only). */
  editing?: boolean;
}

/** The name, description and eligibility criteria of a database; admins edit them here. */
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
  const [eligibilityCriteria, setEligibilityCriteria] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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

  const canSave = name.trim().length > 0 && eligibilityCriteria.trim().length > 0 && !saving;

  const handleSave = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSave) return;
    setSaving(true);
    setError(null);
    try {
      await updateDatabase(database.id, {
        name: name.trim(),
        description: description.trim(),
        eligibilityCriteria: eligibilityCriteria.trim(),
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
      <DialogContent className="sm:max-w-xl">
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
              <Label htmlFor="edit-database-criteria">Eligibility criteria</Label>
              <Textarea
                id="edit-database-criteria"
                value={eligibilityCriteria}
                onChange={(event) => setEligibilityCriteria(event.target.value)}
                placeholder="Which studies belong in it, e.g. study design, population, interventions"
                rows={8}
              />
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
            <section aria-labelledby="database-criteria-heading" className="space-y-2">
              <h3 id="database-criteria-heading" className="text-sm font-medium">
                Eligibility criteria
              </h3>
              <p className="max-h-[50vh] overflow-auto whitespace-pre-line rounded-xl border bg-muted/40 px-3 py-2.5 text-sm">
                {database.eligibilityCriteria}
              </p>
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
