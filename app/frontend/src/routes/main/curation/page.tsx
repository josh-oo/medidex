import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Database, DatabaseZap, Download, FileText, ListChecks, Pencil, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { DatabaseDetailsDialog } from "@/components/databases/database-details-dialog";
import { NewDatabaseDialog } from "@/components/databases/new-database-dialog";
import { CurationList } from "@/components/curation/curation-list";
import { useCuration, type Curation } from "@/hooks/use-curation";
import { exportDatabase } from "@/lib/api/databaseApi";
import { projectDatabaseId, useStudyDatabases, type StudyDatabase } from "@/lib/databases";
import { cn } from "@/lib/utils";

// The maintenance of the study databases in the background: per database its description, its eligibility criteria
// and its projects (batches of new reports), one row each, with what the admin and the assignees have to do next. Tabs
// choose the database shown (kept in the URL as ?db=); admins create databases (empty or imported) and projects here.
export default function DatabaseManagementPage() {
  const curation = useCuration();
  const { loading, isAdmin, projects, tasks, refresh } = curation;
  // The rows fade in only when they had to be waited for; known from before, they are there with the page.
  const [fadeIn] = useState(loading);
  const { loaded: databasesLoaded, failed: databasesFailed, databases } = useStudyDatabases();
  const [params, setParams] = useSearchParams();
  const [newDatabaseOpen, setNewDatabaseOpen] = useState(false);
  const database: StudyDatabase | undefined =
    databases.find((other) => String(other.id) === params.get("db")) ?? databases[0];
  const selectDatabase = (id: number) =>
    setParams(id === databases[0]?.id ? {} : { db: String(id) }, { replace: true });

  // The curation of the shown database only.
  const shown: Curation = {
    ...curation,
    projects: projects.filter((project) => projectDatabaseId(project) === database?.id),
    tasks: tasks.filter((task) => projectDatabaseId(task) === database?.id),
  };
  const isEmpty = shown.projects.length === 0 && shown.tasks.length === 0;

  // A database that is still being indexed takes no projects: their reports would miss its studies.
  const createProjectButton = database?.indexing ? (
    <Button className="gap-2" disabled title={`${database.name} is still being indexed; projects can be added once it is done.`}>
      <Plus className="h-4 w-4" />
      New project
    </Button>
  ) : database && (
    <CreateProjectDialog
      database={database}
      onProjectCreated={refresh}
      trigger={
        <Button className="gap-2">
          <Plus className="h-4 w-4" />
          New project
        </Button>
      }
    />
  );

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
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" className="gap-2" onClick={() => setNewDatabaseOpen(true)}>
                <DatabaseZap className="h-4 w-4" />
                New database
              </Button>
              {createProjectButton}
            </div>
          )}
        </div>

        {databases.length > 1 && (
          <DatabaseTabs databases={databases} selected={database?.id} onSelect={selectDatabase} />
        )}

        {databasesLoaded && !database ? (
          databasesFailed ? (
            <p className="px-1 text-sm text-muted-foreground">The databases could not be loaded.</p>
          ) : (
            <NoDatabases isAdmin={isAdmin} onCreate={() => setNewDatabaseOpen(true)} />
          )
        ) : (
          <section aria-labelledby="database-heading" className="space-y-3">
            {database ? <DatabaseHeader database={database} isAdmin={isAdmin} /> : <Skeleton className="h-5 w-64" />}

            {loading || !database ? (
              <CurationListSkeleton />
            ) : !isEmpty ? (
              <div className={cn(fadeIn && "motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300")}>
                <CurationList curation={shown} />
              </div>
            ) : isAdmin ? (
              <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed bg-card/50 px-6 py-16 text-center">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                  <FileText className="h-6 w-6 text-primary" />
                </div>
                <h3 className="mb-1 text-lg font-semibold">No projects yet</h3>
                <p className="max-w-sm text-sm text-muted-foreground">
                  A project is a batch of new reports to link to the studies of {database.name}. Create one with New
                  project and upload its reports.
                </p>
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed px-4 py-4 text-sm text-muted-foreground">
                Nothing to curate in this database right now. An admin assigns new batches here.
              </div>
            )}
          </section>
        )}
      </div>

      {isAdmin && (
        <NewDatabaseDialog open={newDatabaseOpen} onOpenChange={setNewDatabaseOpen} onCreated={selectDatabase} />
      )}
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
          : "An admin creates the study databases; their projects show up here."}
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

// The name of the database with what it holds and its description; its eligibility criteria (they can be long) in a
// dialog, where admins also edit them, its name and its description. Admins export the database here too.
function DatabaseHeader({ database, isAdmin }: { database: StudyDatabase; isAdmin: boolean }) {
  const [details, setDetails] = useState<"view" | "edit" | null>(null);
  const [exporting, setExporting] = useState(false);

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

  return (
    <div className="space-y-1.5 px-1">
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <Database className="h-4 w-4 shrink-0 text-muted-foreground" />
        <h2 id="database-heading" className="text-sm font-semibold">
          {database.name}
        </h2>
        <span className="text-sm text-muted-foreground">
          {database.numberStudies} {database.numberStudies === 1 ? "study" : "studies"} · {database.numberReports}{" "}
          {database.numberReports === 1 ? "report" : "reports"}
        </span>
        {database.indexing && <IndexingBadge database={database} />}
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1.5 px-2 text-muted-foreground"
            aria-haspopup="dialog"
            onClick={() => setDetails("view")}
          >
            <ListChecks className="h-3.5 w-3.5" />
            Eligibility criteria
          </Button>
          {isAdmin && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 px-2 text-muted-foreground"
              aria-haspopup="dialog"
              onClick={() => setDetails("edit")}
              title="Edit the name, description and eligibility criteria"
            >
              <Pencil className="h-3.5 w-3.5" />
              Edit
            </Button>
          )}
          {isAdmin && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 gap-1.5 px-2 text-muted-foreground"
              disabled={exporting}
              onClick={() => void download()}
              title="Download the studies and reports of this database as a file another Medidex can import"
            >
              <Download className="h-3.5 w-3.5" />
              Export
            </Button>
          )}
        </div>
      </div>
      {database.description && <p className="text-sm text-muted-foreground">{database.description}</p>}
      <DatabaseDetailsDialog
        database={database}
        open={details !== null}
        onOpenChange={(open) => !open && setDetails(null)}
        canEdit={isAdmin}
        editing={details === "edit"}
      />
    </div>
  );
}

// How far the reports of a database are in the vectorstore; until all are, its studies are found by the search but
// not suggested for new reports.
function IndexingBadge({ database }: { database: StudyDatabase }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400"
      title="Its studies are found by the search, but are only suggested for new reports (and take projects) once all its reports are indexed."
    >
      <Spinner className="h-3 w-3" aria-label="Indexing" />
      Indexing {database.numberReportsIndexed} of {database.numberReports}
    </span>
  );
}

// The databases, one tab each.
function DatabaseTabs({
  databases,
  selected,
  onSelect,
}: {
  databases: StudyDatabase[];
  selected?: number;
  onSelect: (id: number) => void;
}) {
  return (
    <div role="tablist" aria-label="Databases" className="flex flex-wrap gap-1">
      {databases.map((database) => (
        <button
          key={database.id}
          type="button"
          role="tab"
          aria-selected={database.id === selected}
          onClick={() => onSelect(database.id)}
          className={cn(
            "rounded-full px-3.5 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            database.id === selected
              ? "bg-card font-medium text-foreground shadow-xs ring-1 ring-border"
              : "text-muted-foreground hover:bg-muted hover:text-foreground"
          )}
        >
          <span className="inline-flex items-center gap-1.5">
            {database.name}
            {database.indexing && <Spinner className="h-3 w-3" aria-label={`${database.name} is being indexed`} />}
          </span>
        </button>
      ))}
    </div>
  );
}

// The project rows while they load, the height of real ones.
function CurationListSkeleton() {
  return (
    <div className="divide-y overflow-hidden rounded-2xl border bg-card shadow-xs" aria-busy="true">
      {Array.from({ length: 3 }, (_, index) => (
        <div key={index} className="flex items-center gap-4 px-4 py-4">
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-4 w-1/3" />
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
