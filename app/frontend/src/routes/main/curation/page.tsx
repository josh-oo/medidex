import { useState } from "react";
import { toast } from "sonner";
import { Database, DatabaseZap, Download, ListChecks, Pencil, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { DatabaseDetailsDialog } from "@/components/databases/database-details-dialog";
import { NewDatabaseDialog } from "@/components/databases/new-database-dialog";
import { CurationList } from "@/components/curation/curation-list";
import { useCuration, type Curation } from "@/hooks/use-curation";
import { exportDatabase } from "@/lib/api/databaseApi";
import { projectDatabaseId, useStudyDatabases, type StudyDatabase } from "@/lib/databases";
import { cn } from "@/lib/utils";

// The maintenance of the study databases in the background: one card per database, with its updates (batches of new
// reports, numbered per database) below it, one row each, with what the admin and the assignees have to do next.
// Admins create databases (empty or imported) here, and the updates on the card of their database.
export default function DatabaseManagementPage() {
  const curation = useCuration();
  const { loading, isAdmin } = curation;
  // The rows fade in only when they had to be waited for; known from before, they are there with the page.
  const [fadeIn] = useState(loading);
  const { loaded: databasesLoaded, failed: databasesFailed, databases } = useStudyDatabases();
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
        ) : databases.length === 0 ? (
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
  const { loading, isAdmin, projects, tasks, refresh } = curation;
  const [details, setDetails] = useState<"view" | "edit" | null>(null);
  const [exporting, setExporting] = useState(false);

  // The curation of this database only.
  const own: Curation = {
    ...curation,
    projects: projects.filter((project) => projectDatabaseId(project) === database.id),
    tasks: tasks.filter((task) => projectDatabaseId(task) === database.id),
  };
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

  const newUpdateLabel = (
    <>
      <Plus className="h-4 w-4" />
      New update
    </>
  );
  // A database that is still being indexed takes no updates: their reports would miss its studies.
  const newUpdateButton = database.indexing ? (
    <Button size="sm" className="gap-1.5" disabled title={`${database.name} is still being indexed; updates can be added once it is done.`}>
      {newUpdateLabel}
    </Button>
  ) : (
    <CreateProjectDialog
      database={database}
      number={nextUpdateNumber(own.projects.map((project) => project.name))}
      onProjectCreated={refresh}
      trigger={
        <Button size="sm" className="gap-1.5">
          {newUpdateLabel}
        </Button>
      }
    />
  );

  return (
    <section
      aria-labelledby={`database-${database.id}`}
      className="overflow-hidden rounded-2xl border bg-card shadow-xs"
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-primary/10">
          <Database className="h-5 w-5 text-primary" aria-hidden />
        </span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
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
            {database.indexing && <IndexingBadge database={database} />}
          </div>
          <span className="text-xs text-muted-foreground">
            {database.numberStudies} {database.numberStudies === 1 ? "study" : "studies"} · {database.numberReports}{" "}
            {database.numberReports === 1 ? "report" : "reports"} · {updateCount} {updateCount === 1 ? "update" : "updates"}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-1">
          <CardAction icon={ListChecks} label="Eligibility criteria" onClick={() => setDetails("view")} dialog />
          {isAdmin && (
            <CardAction
              icon={Pencil}
              label="Edit the name, description and eligibility criteria"
              onClick={() => setDetails("edit")}
              dialog
            />
          )}
          {isAdmin && (
            <CardAction
              icon={Download}
              label="Export: the studies and reports as a file another Medidex can import"
              onClick={() => void download()}
              disabled={exporting}
            />
          )}
          {isAdmin && <div className="ml-2">{newUpdateButton}</div>}
        </div>
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
                  {isAdmin
                    ? "No updates yet. New update uploads a batch of new reports to link to the studies of this database."
                    : "Nothing to curate in this database right now."}
                </p>
              }
            />
          </div>
        )}
      </div>

      <DatabaseDetailsDialog
        database={database}
        open={details !== null}
        onOpenChange={(open) => !open && setDetails(null)}
        canEdit={isAdmin}
        editing={details === "edit"}
      />
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

// How far the reports of a database are in the vectorstore; until all are, its studies are found by the search but
// not suggested for new reports.
function IndexingBadge({ database }: { database: StudyDatabase }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400"
      title="Its studies are found by the search, but are only suggested for new reports (and take updates) once all its reports are indexed."
    >
      <Spinner className="h-3 w-3" aria-label="Indexing" />
      Indexing {database.numberReportsIndexed} of {database.numberReports}
    </span>
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
