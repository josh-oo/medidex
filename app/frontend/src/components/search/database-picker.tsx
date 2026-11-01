import { useState } from "react";
import { ChevronDown, Database } from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useStudyDatabases } from "@/lib/databases";
import { cn } from "@/lib/utils";

interface DatabasePickerProps {
  /** The ids of the chosen databases; empty means all of them. */
  selected: number[];
  onChange: (selected: number[]) => void;
  /** The size of the search bar it sits in. */
  size?: "hero" | "compact";
}

/**
 * The databases to search, as a round button at the start of the search bar that names them. Databases are created on the database
 * management page.
 */
export function DatabasePicker({ selected, onChange, size = "compact" }: DatabasePickerProps) {
  const { databases } = useStudyDatabases();
  const [open, setOpen] = useState(false);

  const chosen = databases.filter((database) => selected.length === 0 || selected.includes(database.id));
  const label =
    chosen.length === databases.length ? "All databases" : chosen.map((database) => database.name).join(", ");

  const toggle = (id: number) => {
    const current = chosen.map((database) => database.id);
    const next = current.includes(id) ? current.filter((other) => other !== id) : [...current, id];
    // At least one stays chosen; all of them is the default.
    if (next.length === 0) return;
    onChange(next.length === databases.length ? [] : next);
  };

  return (
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
          <Database className="h-4 w-4 shrink-0" aria-hidden />
          <span
            className={cn(
              "max-w-[10rem] truncate text-sm",
              size === "hero" ? "ml-0.5 hidden sm:inline" : "ml-0.5 hidden md:inline"
            )}
          >
            {label}
          </span>
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
      </PopoverContent>
    </Popover>
  );
}
