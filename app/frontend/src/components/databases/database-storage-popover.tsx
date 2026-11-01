import { useEffect, useState } from "react";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { getDatabaseStorage } from "@/lib/api/databaseApi";
import type { StudyDatabase } from "@/lib/databases";
import type { DatabaseStorageDto, StorageUsageDto } from "@/types/apiDTOs";
import { cn } from "@/lib/utils";

const UNITS = ["B", "KB", "MB", "GB", "TB"];

function formatBytes(bytes: number): string {
  const exponent = bytes > 0 ? Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), UNITS.length - 1) : 0;
  const value = bytes / 1024 ** exponent;
  return `${value.toLocaleString(undefined, { maximumFractionDigits: exponent === 0 || value >= 100 ? 0 : 1 })} ${UNITS[exponent]}`;
}

const count = (value: number, one: string, many: string) => `${value.toLocaleString()} ${value === 1 ? one : many}`;

// The lines of a part of the storage; extras are what the extensions keep elsewhere (e.g. chat histories).
function lines(usage: StorageUsageDto) {
  return [
    { label: "Data", bytes: usage.dataBytes },
    { label: "Search index", bytes: usage.searchIndexBytes },
    { label: `PDFs (${count(usage.pdfFiles, "file", "files")})`, bytes: usage.pdfBytes },
    ...usage.extras,
  ];
}

const usageTotal = (usage: StorageUsageDto) => lines(usage).reduce((sum, line) => sum + line.bytes, 0);

function Part({ title, usage, color }: { title: string; usage: StorageUsageDto; color: string }) {
  return (
    <section className="space-y-1.5">
      <div className="flex items-center gap-2 text-sm">
        <span aria-hidden className={cn("h-2.5 w-2.5 shrink-0 rounded-full", color)} />
        <span className="min-w-0 flex-1 font-medium">{title}</span>
        <span className="font-medium tabular-nums">{formatBytes(usageTotal(usage))}</span>
      </div>
      <ul className="space-y-0.5 pl-[18px] text-xs">
        {lines(usage).map((line) => (
          <li key={line.label} className="flex justify-between gap-3">
            <span className="text-muted-foreground">{line.label}</span>
            <span className="tabular-nums">{formatBytes(line.bytes)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The (i) next to the name of a database (admins only): what the database takes in storage, split into what stays and
 * what only its updates need, asked for every time it opens. */
export function DatabaseStoragePopover({ database }: { database: StudyDatabase }) {
  const [open, setOpen] = useState(false);
  const [storage, setStorage] = useState<DatabaseStorageDto | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!open) return;
    let current = true;
    setFailed(false);
    getDatabaseStorage(database.id)
      .then((found) => current && setStorage(found))
      .catch(() => current && setFailed(true));
    return () => {
      current = false;
    };
  }, [open, database.id]);

  const stays = storage ? usageTotal(storage.database) : 0;
  const temporary = storage ? usageTotal(storage.updates) : 0;
  const total = stays + temporary;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="icon-sm" className="-ml-1 size-6 text-muted-foreground" aria-label="Storage">
              <Info className="h-3.5 w-3.5" />
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent>Storage</TooltipContent>
      </Tooltip>
      <PopoverContent
        align="start"
        sideOffset={8}
        className="w-[min(320px,calc(100vw-2rem))] rounded-2xl border bg-popover p-4 text-popover-foreground shadow-lg"
      >
        <div className="space-y-4">
          <div>
            <p className="text-xs font-medium text-muted-foreground">Storage of {database.name}</p>
            {storage ? (
              <p className="mt-1 text-xl font-semibold tabular-nums">{formatBytes(total)}</p>
            ) : failed ? (
              <p role="alert" className="mt-1 text-sm text-destructive">
                The storage could not be loaded.
              </p>
            ) : (
              <Skeleton className="mt-1.5 h-6 w-28" />
            )}
          </div>

          {storage ? (
            <>
              <div aria-hidden className="flex h-2 gap-0.5 overflow-hidden rounded-full bg-muted">
                {stays > 0 && <div className="bg-chart-3" style={{ width: `${Math.max((stays / total) * 100, 2)}%` }} />}
                {temporary > 0 && (
                  <div className="bg-chart-1" style={{ width: `${Math.max((temporary / total) * 100, 2)}%` }} />
                )}
              </div>
              <Part title="Core database" usage={storage.database} color="bg-chart-3" />
              {storage.numberUpdates > 0 ? (
                <Part title="Open updates" usage={storage.updates} color="bg-chart-1" />
              ) : (
                <p className="text-xs text-muted-foreground">No open updates.</p>
              )}
              <p className="text-xs text-muted-foreground">
                Estimates. Data shared by all databases, such as the tags, is not counted.
              </p>
            </>
          ) : (
            !failed && (
              <div className="space-y-2.5" aria-busy="true">
                <Skeleton className="h-2 w-full" />
                {Array.from({ length: 2 }, (_, index) => (
                  <Skeleton key={index} className="h-16 w-full" />
                ))}
              </div>
            )
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
