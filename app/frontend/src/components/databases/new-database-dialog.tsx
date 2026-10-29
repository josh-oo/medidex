import { useRef, useState, type FormEvent } from "react";
import axios from "axios";
import { toast } from "sonner";
import { FileJson, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { createDatabase, importDatabase } from "@/lib/api/databaseApi";
import { readZipEntry } from "@/lib/zip";
import { refreshStudyDatabases } from "@/lib/databases";
import type { DatabaseDto } from "@/types/apiDTOs";

interface NewDatabaseDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the id of the new database once it exists. */
  onCreated?: (id: number) => void;
}

// What the backend says is wrong with the request (e.g. why an import file was rejected), if it says.
function errorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error) && typeof error.response?.data?.detail === "string") return error.response.data.detail;
  return fallback;
}

/**
 * Creates a study database with the studies, reports and PDFs of an exported database (a .medidex.zip archive, see
 * GET /databases/{id}/export, or its database.json alone), or an empty one if no file is chosen (after asking).
 * Admins only.
 */
export function NewDatabaseDialog({ open, onOpenChange, onCreated }: NewDatabaseDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [eligibilityCriteria, setEligibilityCriteria] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileSummary, setFileSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [confirmEmpty, setConfirmEmpty] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const reset = () => {
    setName("");
    setDescription("");
    setEligibilityCriteria("");
    setFile(null);
    setFileSummary(null);
    setError(null);
  };

  // An exported database names and describes itself: those fill the fields that are still empty.
  const chooseFile = async (chosen: File | null) => {
    setFile(chosen);
    setFileSummary(null);
    setError(null);
    if (!chosen) return;
    try {
      // An archive (database.json and its PDFs) or a database.json alone.
      const document = chosen.name.toLowerCase().endsWith(".json")
        ? await chosen.text()
        : await readZipEntry(chosen, "database.json").then((bytes) => (bytes ? new TextDecoder().decode(bytes) : null));
      if (document === null) {
        setError("This is no exported Medidex database (a .medidex.zip archive with a database.json).");
        return;
      }
      const data = JSON.parse(document);
      if (data?.format !== "medidex-database") {
        setError('This is no exported Medidex database (its database.json has no "format": "medidex-database").');
        return;
      }
      if (typeof data.name === "string" && !name.trim()) setName(data.name);
      if (typeof data.description === "string" && !description.trim()) setDescription(data.description);
      if (typeof data.eligibilityCriteria === "string" && !eligibilityCriteria.trim())
        setEligibilityCriteria(data.eligibilityCriteria);
      const studies: { reports?: { pdf?: string | null }[] }[] = Array.isArray(data.studies) ? data.studies : [];
      const reports = studies.flatMap((study) => (Array.isArray(study.reports) ? study.reports : []));
      const pdfs = reports.filter((report) => report.pdf).length;
      setFileSummary(`${studies.length} studies, ${reports.length} reports, ${pdfs} PDFs`);
    } catch {
      setError("The database.json of the file is no JSON.");
    }
  };

  const canSubmit = name.trim().length > 0 && eligibilityCriteria.trim().length > 0 && !submitting;

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    // Without a file the database starts empty, which is easy to do by mistake.
    if (file) void submit();
    else setConfirmEmpty(true);
  };

  const submit = async () => {
    setConfirmEmpty(false);
    setSubmitting(true);
    setError(null);
    const payload = {
      name: name.trim(),
      description: description.trim() || null,
      eligibilityCriteria: eligibilityCriteria.trim(),
    };
    try {
      const database: DatabaseDto = file ? await importDatabase(file, payload) : await createDatabase(payload);
      await refreshStudyDatabases();
      toast.success(`Database "${database.name}" created`, {
        description: file
          ? `${database.numberStudies} studies and ${database.numberReports} reports imported. They are suggested for new reports once indexed.`
          : undefined,
      });
      onCreated?.(database.databaseId);
      reset();
      onOpenChange(false);
    } catch (submitError) {
      setError(errorMessage(submitError, file ? "The import failed." : "The database could not be created."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (submitting) return;
        if (!nextOpen) reset();
        onOpenChange(nextOpen);
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New database</DialogTitle>
            <DialogDescription>
              A separate collection of studies with its own projects. New reports are only matched against the studies
              of their project's database. Import an exported database, or leave out the file to start empty.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="database-file">Exported database (optional)</Label>
            <input
              ref={fileInput}
              id="database-file"
              type="file"
              accept=".zip,application/zip,.json,application/json"
              className="sr-only"
              onChange={(event) => void chooseFile(event.target.files?.[0] ?? null)}
            />
            {file ? (
              <div className="flex items-center gap-3 rounded-lg border bg-muted/40 px-3 py-2">
                <FileJson className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{file.name}</p>
                  {fileSummary && <p className="text-xs text-muted-foreground">{fileSummary}</p>}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  aria-label="Remove file"
                  onClick={() => {
                    if (fileInput.current) fileInput.current.value = "";
                    void chooseFile(null);
                  }}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                className="flex w-full flex-col items-center gap-1 rounded-lg border border-dashed px-4 py-5 text-center text-sm text-muted-foreground transition-colors hover:bg-muted/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <FileJson className="h-5 w-5" aria-hidden />
                <span>
                  Choose a <span className="font-medium text-foreground">.medidex.zip</span> file
                </span>
                <span className="text-xs">
                  Exported from the database management of a Medidex, with the PDFs of its reports.
                </span>
              </button>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="database-name">Name</Label>
            <Input
              id="database-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Oncology trials"
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="database-description">Description</Label>
            <Textarea
              id="database-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What it collects (optional)"
              rows={2}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="database-criteria">Eligibility criteria</Label>
            <Textarea
              id="database-criteria"
              value={eligibilityCriteria}
              onChange={(event) => setEligibilityCriteria(event.target.value)}
              placeholder="Which studies belong in it, e.g. study design, population, interventions"
              rows={4}
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
              onClick={() => {
                reset();
                onOpenChange(false);
              }}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {submitting ? (file ? "Importing…" : "Creating…") : file ? "Import database" : "Create database"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>

      <AlertDialog open={confirmEmpty} onOpenChange={setConfirmEmpty}>
        <AlertDialogContent className="sm:max-w-sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Create an empty database?</AlertDialogTitle>
            <AlertDialogDescription>
              No file is chosen, so &quot;{name.trim()}&quot; starts without studies. Its studies come from the projects
              uploaded into it.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Back</AlertDialogCancel>
            <AlertDialogAction onClick={() => void submit()}>Create empty database</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
