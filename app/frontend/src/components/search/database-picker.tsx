import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { ChevronDown, Database, DatabaseZap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useAuthStore } from "@/hooks/use-auth";
import { addStudyDatabase, useStudyDatabases } from "@/lib/databases";
import { cn } from "@/lib/utils";

interface DatabasePickerProps {
  /** The ids of the chosen databases; empty means all of them. */
  selected: string[];
  onChange: (selected: string[]) => void;
  /** The size of the search bar it sits in. */
  size?: "hero" | "compact";
}

/**
 * The databases to search, as a round button at the start of the search bar. Its menu also lets admins create a new
 * database (a mock for now).
 */
export function DatabasePicker({ selected, onChange, size = "compact" }: DatabasePickerProps) {
  const databases = useStudyDatabases();
  const isAdmin = useAuthStore((s) => s.user?.isAdmin ?? false);
  const [open, setOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const chosen = databases.filter((database) => selected.length === 0 || selected.includes(database.id));
  const label =
    chosen.length === databases.length ? "All databases" : chosen.map((database) => database.name).join(", ");

  const toggle = (id: string) => {
    const current = chosen.map((database) => database.id);
    const next = current.includes(id) ? current.filter((other) => other !== id) : [...current, id];
    // At least one stays chosen; all of them is the default.
    if (next.length === 0) return;
    onChange(next.length === databases.length ? [] : next);
  };

  return (
    <>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label={`Databases: ${label}`}
            title={label}
            className={cn(
              "flex shrink-0 items-center justify-center gap-1 rounded-full bg-muted text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/60",
              size === "hero" ? "h-10 px-3" : "h-8 px-2.5"
            )}
          >
            <Database className="h-4 w-4" aria-hidden />
            <ChevronDown className="h-3 w-3" aria-hidden />
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          sideOffset={10}
          className="w-64 rounded-2xl border bg-popover p-1.5 text-popover-foreground shadow-lg"
        >
          <p className="px-2 pb-1 pt-1.5 text-xs font-medium text-muted-foreground">Search in</p>
          {databases.map((database) => (
            <label
              key={database.id}
              className="flex cursor-pointer items-center gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
            >
              <Checkbox
                checked={chosen.some((other) => other.id === database.id)}
                onCheckedChange={() => toggle(database.id)}
              />
              <span className="min-w-0 flex-1 truncate">{database.name}</span>
            </label>
          ))}

          {isAdmin && (
            <>
              <div className="my-1.5 h-px bg-border" />
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  setCreateOpen(true);
                }}
                className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted"
              >
                <DatabaseZap className="h-4 w-4 text-muted-foreground" aria-hidden />
                New database…
              </button>
            </>
          )}
        </PopoverContent>
      </Popover>

      {isAdmin && (
        <NewDatabaseDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreated={(id) => onChange([...chosen.map((database) => database.id), id])}
        />
      )}
    </>
  );
}

// A mock: the database only lives in this session, as the backend cannot hold more than one yet.
function NewDatabaseDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (id: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    const database = addStudyDatabase(name, description);
    onCreated(database.id);
    toast.success(`Database "${database.name}" created`, {
      description: "A preview: it is only kept until the page is reloaded.",
    });
    setName("");
    setDescription("");
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New database</DialogTitle>
            <DialogDescription>
              A separate collection of studies with its own reports and projects. This is a preview: the database is
              not saved yet.
            </DialogDescription>
          </DialogHeader>
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
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim()}>
              Create database
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
