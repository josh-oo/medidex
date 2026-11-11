import { useState } from "react";
import { toast } from "sonner";
import { Database, DatabaseZap, Download, ListChecks, MoreHorizontal, Pencil, Plus, UserRoundCog } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { DatabaseDetailsDialog } from "@/components/databases/database-details-dialog";
import { DatabaseStoragePopover } from "@/components/databases/database-storage-popover";
import { NewDatabaseDialog } from "@/components/databases/new-database-dialog";
import { CurationList } from "@/components/curation/curation-list";
import { useCuration, type Curation } from "@/hooks/use-curation";
import { useMediaQuery } from "@/hooks/use-media-query";
import { exportDatabase, transferDatabase } from "@/lib/api/databaseApi";
import { TransferOwnerDialog } from "@/components/auth/transfer-owner-dialog";
import { useAuthStore } from "@/hooks/use-auth";
import { projectDatabaseId, refreshStudyDatabases, useStudyDatabases, type DatabaseUpload, type StudyDatabase } from "@/lib/databases";
import { cn } from "@/lib/utils";

// The maintenance of the study databases in the background: one card per database, with its updates (batches of new
// reports, numbered per database) below it, one row each, with what the owner and the assignees have to do next.
// Admins create databases (empty or imported) here; the owner of a database adds its updates on its card.
export default function DatabaseManagementPage() {
  const curation = useCuration();
  const { loading, isAdmin } = curation;
  // The rows fade in only when they had to be waited for; known from before, they are there with the page.
  const [fadeIn] = useState(loading);
  const { loaded: databasesLoaded, failed: databasesFailed, databases, uploads } = useStudyDatabases();
  const [newDatabaseOpen, setNewDatabaseOpen] = useState(false);

  return (
    <div className="flex-1 overflow-auto">
      <div className="mx-auto max-w-6xl space-y-6 px-4 pb-10 pt-4 md:px-8 md:pt-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Database management</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              New batches of reports, linked to their studies to keep the databases up to date.
            </p>
          </div>
          {isAdmin && (
            <Button variant="outline" className="gap-2" onClick={() => setNewDatabaseOpen(true)}>
              <DatabaseZap className="h-4 w-4" />
              New database
            </Button>
          )}
        </div>

        {!databasesLoaded ? (
          <DatabaseCardSkeleton />
        ) : databases.length === 0 && uploads.length === 0 ? (
          databasesFailed ? (
            <p className="px-1 text-sm text-muted-foreground">The databases could not be loaded.</p>
          ) : (
            <NoDatabases isAdmin={isAdmin} onCreate={() => setNewDatabaseOpen(true)} />
          )
        ) : (
          <TooltipProvider>
            <div className="space-y-4">
              {databases.map((database) => (
                <DatabaseCard
                  key={database.id}
                  database={database}
                  curation={curation}
                  fadeIn={fadeIn}
                />
              ))}
              {uploads.map((upload) => (
                <UploadCard key={upload.key} upload={upload} />
              ))}
            </div>
          </TooltipProvider>
        )}
      </div>

      {isAdmin && <NewDatabaseDialog open={newDatabaseOpen} onOpenChange={setNewDatabaseOpen} />}
    </div>
  );
}

// Before the first database: every deployment creates (or imports) its own.
function NoDatabases({ isAdmin, onCreate }: { isAdmin: boolean; onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed bg-card/50 px-6 py-16 text-center">
      <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
        <Database className="h-6 w-6 text-primary" />
      </div>
      <h3 className="mb-1 text-lg font-semibold">No databases yet</h3>
      <p className="max-w-sm text-sm text-muted-foreground">
        {isAdmin
          ? "A database is a collection of studies, e.g. the register of a review group. Create an empty one or import an exported database to start."
          : "An admin creates the study databases; their updates show up here."}
      </p>
      {isAdmin && (
        <Button className="mt-6 gap-2" onClick={onCreate}>
          <DatabaseZap className="h-4 w-4" />
          New database
        </Button>
      )}
    </div>
  );
}

// The number of the next update of a database: one more than the highest so far, deleted updates keep theirs.
function nextUpdateNumber(names: string[]): number {
  const numbers = names.map((name) => Number(/^Update (\d+)$/.exec(name)?.[1] ?? 0));
  return Math.max(names.length, ...numbers) + 1;
}

// A database: its name (the description shows on hovering it), what it holds and its actions, with its updates below.
// Its eligibility criteria (they can be long) are in a dialog, where admins also edit them, its name and description.
function DatabaseCard({ database, curation, fadeIn }: { database: StudyDatabase; curation: Curation; fadeIn: boolean }) {
  const { loading, projects, tasks, assignableUsers, refresh } = curation;
  const userId = useAuthStore((s) => s.user?.id);
  // Its owner changes, exports and transfers it, and uploads, assigns and merges its updates.
  const isOwner = Boolean(userId) && database.owner === userId;
  const [transferOpen, setTransferOpen] = useState(false);
  const [details, setDetails] = useState<"view" | "edit" | null>(null);
  const [exporting, setExporting] = useState(false);
  const [newUpdateOpen, setNewUpdateOpen] = useState(false);
  // On a phone the actions are in a menu, where they leave the name its room.
  const wide = useMediaQuery("(min-width: 640px)");

  // The curation of this database only.
  const own: Curation = {
    ...curation,
    projects: projects.filter((project) => projectDatabaseId(project) === database.id),
    tasks: tasks.filter((task) => projectDatabaseId(task) === database.id),
  };
  // The owner is an approved user, so among the users an update can be assigned to.
  const ownerName = isOwner ? "you" : assignableUsers.find((user) => user.id === database.owner)?.name;
  const updateCount = new Set([...own.projects, ...own.tasks].map((update) => update.projectId)).size;

  const download = async () => {
    setExporting(true);
    try {
      const blob = await exportDatabase(database.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${
        database.name
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, "") || "database"
      }.medidex.zip`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error(`The export of ${database.name} failed.`);
    } finally {
      setExporting(false);
    }
  };

  // A database that is still being imported or indexed takes no updates: their reports would miss its studies.
  const busy = database.importing || database.indexing;
  const busyTitle = database.indexingError
    ? `The indexing of ${database.name} failed; updates can be added once it is indexed.`
    : `${database.name} is still being ${database.importing ? "imported" : "indexed"}; updates can be added once it is done.`;

  const actions = wide ? (
    <div className="ml-auto flex shrink-0 items-center gap-1">
      {/* Its owner sees the eligibility criteria in the edit dialog. */}
      {!isOwner && (
        <CardAction icon={ListChecks} label="Eligibility criteria" onClick={() => setDetails("view")} dialog />
      )}
      {isOwner && (
        <CardAction
          icon={Pencil}
          label="Edit the name, description and eligibility criteria"
          onClick={() => setDetails("edit")}
          disabled={database.importing}
          dialog
        />
      )}
      {isOwner && (
        <CardAction
          icon={Download}
          label="Export: the studies and reports as a file another Medidex can import"
          onClick={() => void download()}
          disabled={exporting || database.importing}
        />
      )}
      {isOwner && (
        <CardAction
          icon={UserRoundCog}
          label="Transfer database ownership"
          onClick={() => setTransferOpen(true)}
          disabled={database.importing}
          dialog
        />
      )}
      {isOwner && (
        <Button
          size="sm"
          className="ml-2 gap-1.5"
          disabled={busy}
          title={busy ? busyTitle : undefined}
          aria-haspopup="dialog"
          onClick={() => setNewUpdateOpen(true)}
        >
          <Plus className="h-4 w-4" />
          New update
        </Button>
      )}
    </div>
  ) : (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="ml-auto shrink-0" aria-label={`Actions for ${database.name}`}>
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        {isOwner && (
          <>
            <DropdownMenuItem disabled={busy} onSelect={() => setNewUpdateOpen(true)}>
              <Plus className="h-4 w-4" />
              New update…
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        )}
        {!isOwner && (
          <DropdownMenuItem onSelect={() => setDetails("view")}>
            <ListChecks className="h-4 w-4" />
            Eligibility criteria…
          </DropdownMenuItem>
        )}
        {isOwner && (
          <DropdownMenuItem disabled={database.importing} onSelect={() => setDetails("edit")}>
            <Pencil className="h-4 w-4" />
            Edit…
          </DropdownMenuItem>
        )}
        {isOwner && (
          <DropdownMenuItem disabled={exporting || database.importing} onSelect={() => void download()}>
            <Download className="h-4 w-4" />
            Export
          </DropdownMenuItem>
        )}
        {isOwner && (
          <DropdownMenuItem disabled={database.importing} onSelect={() => setTransferOpen(true)}>
            <UserRoundCog className="h-4 w-4" />
            Transfer ownership…
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );

  return (
    <section
      aria-labelledby={`database-${database.id}`}
      className="overflow-hidden rounded-2xl border bg-card shadow-xs"
    >
      <header className="flex items-center gap-3 px-4 py-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary/10">
          <Database className="h-5 w-5 text-primary" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          {/* The (i) stays right after the name, which gives way; the progress of an import wraps below them. */}
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
            <div className="flex min-w-0 max-w-full items-center gap-1">
              <h2 id={`database-${database.id}`} className="min-w-0 truncate text-base font-semibold">
                {database.description ? (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span
                        tabIndex={0}
                        className="cursor-help rounded-sm underline decoration-muted-foreground/40 decoration-dotted underline-offset-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
                      >
                        {database.name}
                      </span>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" align="start" sideOffset={6} className="max-w-sm text-left text-sm">
                      {database.description}
                    </TooltipContent>
                  </Tooltip>
                ) : (
                  database.name
                )}
              </h2>
              {isOwner && !database.importing && <DatabaseStoragePopover database={database} />}
            </div>
            {(database.importing || database.indexing) && <ProgressBadge database={database} />}
          </div>
          <span className="truncate text-xs text-muted-foreground">
            {database.numberStudies} {database.numberStudies === 1 ? "study" : "studies"} · {database.numberReports}{" "}
            {database.numberReports === 1 ? "report" : "reports"} · {updateCount} {updateCount === 1 ? "update" : "updates"}
            {ownerName && <> · Owner: {ownerName}</>}
          </span>
        </div>
        {actions}
      </header>

      <div className="border-t">
        {loading ? (
          <UpdateRowsSkeleton />
        ) : (
          <div className={cn(fadeIn && "motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300")}>
            <CurationList
              curation={own}
              empty={
                <p className="px-4 py-6 text-center text-sm text-muted-foreground">
                  {isOwner
                    ? "No updates yet. New update uploads a batch of new reports to link to the studies of this database."
                    : "Nothing to curate in this database right now."}
                </p>
              }
            />
          </div>
        )}
      </div>

      {isOwner && !busy && (
        <CreateProjectDialog
          database={database}
          number={nextUpdateNumber(own.projects.map((project) => project.name))}
          onProjectCreated={refresh}
          open={newUpdateOpen}
          onOpenChange={setNewUpdateOpen}
        />
      )}
      <DatabaseDetailsDialog
        database={database}
        open={details !== null}
        onOpenChange={(open) => !open && setDetails(null)}
        canEdit={isOwner}
        editing={details === "edit"}
      />
      {isOwner && (
        <TransferOwnerDialog
          open={transferOpen}
          onOpenChange={setTransferOpen}
          name={database.name}
          onTransfer={async (ownerId) => {
            await transferDatabase(database.id, ownerId);
            await refreshStudyDatabases();
            // Its updates are no longer among the user's projects.
            refresh();
          }}
        />
      )}
    </section>
  );
}

// An icon button in the header of a database card, named by its tooltip.
function CardAction({
  icon: Icon,
  label,
  onClick,
  disabled,
  dialog,
}: {
  icon: typeof Database;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  dialog?: boolean;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          className="text-muted-foreground"
          aria-label={label}
          aria-haspopup={dialog ? "dialog" : undefined}
          disabled={disabled}
          onClick={onClick}
        >
          <Icon className="h-4 w-4" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

const IMPORT_STEPS = { studies: "studies", reports: "reports", pdfs: "PDFs" } as const;

const count = (done: number, total: number) => `${done.toLocaleString()} of ${total.toLocaleString()}`;

// A number of bytes as people read it, e.g. "6.2 GB".
function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

// How far the import of a database is (its studies, its reports, then their PDFs), and then how far its reports are in
// the vectorstore; until all are, its studies are found by the search but not suggested for new reports.
function ProgressBadge({ database }: { database: StudyDatabase }) {
  const { status } = database;
  if (database.importing) {
    return (
      <StatusChip
        label={status?.step ? `Importing ${IMPORT_STEPS[status.step]} ${count(status.done, status.total)}` : "Importing…"}
        busy="Importing"
        title="Nothing of it is kept before its studies and reports all are; it takes updates once it is imported and indexed."
      />
    );
  }
  if (database.indexingError) {
    return (
      <StatusChip
        label={`Indexing failed at ${count(database.numberReportsIndexed, database.numberReports)}`}
        title={`${database.indexingError} It is tried again when the backend starts again.`}
        failed
      />
    );
  }
  return (
    <StatusChip
      label={`Indexing ${count(database.numberReportsIndexed, database.numberReports)}`}
      busy="Indexing"
      title="Its studies are found by the search, but are only suggested for new reports (and take updates) once all its reports are indexed."
    />
  );
}

function StatusChip({ label, busy, title, failed }: { label: string; busy?: string; title: string; failed?: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
        failed ? "bg-destructive/10 text-destructive" : "bg-amber-500/10 text-amber-700 dark:text-amber-400",
      )}
      title={title}
    >
      {!failed && <Spinner className="h-3 w-3" aria-label={busy} />}
      {label}
    </span>
  );
}

// An imported database while its file is uploaded: it has no id, numbers or updates yet. Once the file is in, the card
// of the database follows its import.
function UploadCard({ upload }: { upload: DatabaseUpload }) {
  const percent = upload.total ? Math.floor((100 * upload.loaded) / upload.total) : 0;
  return (
    <section aria-label={upload.name} className="overflow-hidden rounded-2xl border bg-card shadow-xs">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary/10">
          <Database className="h-5 w-5 text-primary" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="min-w-0 truncate text-base font-semibold">{upload.name}</h2>
            <StatusChip
              label={
                upload.loaded < upload.total
                  ? `Uploading ${formatBytes(upload.loaded)} of ${formatBytes(upload.total)} (${percent}%)`
                  : "Uploaded, the import starts…"
              }
              busy="Uploading"
              title="Leaving or reloading this page ends the upload; once the file is uploaded, the import goes on without it."
            />
          </div>
          <span className="text-xs text-muted-foreground">Its file is being uploaded.</span>
        </div>
      </header>
    </section>
  );
}

// A database card while the databases load.
function DatabaseCardSkeleton() {
  return (
    <div className="overflow-hidden rounded-2xl border bg-card shadow-xs" aria-busy="true">
      <div className="flex items-center gap-3 px-4 py-3">
        <Skeleton className="h-10 w-10 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3 w-32" />
        </div>
      </div>
      <div className="border-t">
        <UpdateRowsSkeleton />
      </div>
    </div>
  );
}

// The update rows while they load, the height of real ones.
function UpdateRowsSkeleton() {
  return (
    <div className="divide-y" aria-busy="true">
      {Array.from({ length: 2 }, (_, index) => (
        <div key={index} className="flex items-center gap-4 px-4 py-3">
          <Skeleton className="h-10 w-10 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-1/4" />
            <Skeleton className="h-3 w-1/5" />
          </div>
          <div className="flex gap-3">
            {Array.from({ length: 3 }, (_, ring) => (
              <Skeleton key={ring} className="h-10 w-10 rounded-full" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
