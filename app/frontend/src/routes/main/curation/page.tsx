import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Database, FileText, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CreateProjectDialog } from "@/components/projects/create-project-dialog";
import { CurationList } from "@/components/curation/curation-list";
import { useCuration, type Curation } from "@/hooks/use-curation";
import { DEFAULT_DATABASE_ID, projectDatabaseId, useStudyDatabases, type StudyDatabase } from "@/lib/databases";
import { cn } from "@/lib/utils";

// The maintenance of the study databases in the background: per database its projects (batches of new reports), one
// row each, with what the admin and the assignees have to do next. With more than one database, tabs choose the one
// shown (kept in the URL as ?db=).
export default function DatabaseManagementPage() {
  const curation = useCuration();
  const { loading, isAdmin, projects, tasks, refresh } = curation;
  // The rows fade in only when they had to be waited for; known from before, they are there with the page.
  const [fadeIn] = useState(loading);
  const databases = useStudyDatabases();
  const [params, setParams] = useSearchParams();
  const database = databases.find((other) => other.id === params.get("db")) ?? databases[0];
  // New projects go to the database there is today (see projectDatabaseId).
  const canCreateHere = database.id === DEFAULT_DATABASE_ID;

  // The curation of the shown database only.
  const shown: Curation = {
    ...curation,
    projects: projects.filter((project) => projectDatabaseId(project) === database.id),
    tasks: tasks.filter((task) => projectDatabaseId(task) === database.id),
  };
  const isEmpty = shown.projects.length === 0 && shown.tasks.length === 0;

  const createProjectButton = (
    <CreateProjectDialog
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
              New batches of reports, linked to their studies to keep the database up to date.
            </p>
          </div>
          {isAdmin && canCreateHere && !loading && !isEmpty && createProjectButton}
        </div>

        {databases.length > 1 && (
          <DatabaseTabs
            databases={databases}
            selected={database.id}
            onSelect={(id) => setParams(id === databases[0].id ? {} : { db: id }, { replace: true })}
          />
        )}

        <section aria-labelledby="database-heading" className="space-y-3">
          <div className="flex min-w-0 items-baseline gap-2 px-1">
            <Database className="h-4 w-4 shrink-0 self-center text-muted-foreground" />
            <h2 id="database-heading" className="text-sm font-semibold">
              {database.name}
            </h2>
            {database.description && (
              <p className="min-w-0 truncate text-sm text-muted-foreground">{database.description}</p>
            )}
          </div>

          {loading ? (
            <CurationListSkeleton />
          ) : !isEmpty ? (
            <div className={cn(fadeIn && "motion-safe:animate-in motion-safe:fade-in motion-safe:duration-300")}>
              <CurationList curation={shown} />
            </div>
          ) : isAdmin && canCreateHere ? (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed bg-card/50 px-6 py-16 text-center">
              <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                <FileText className="h-6 w-6 text-primary" />
              </div>
              <h3 className="mb-1 text-lg font-semibold">No projects yet</h3>
              <p className="mb-6 max-w-sm text-sm text-muted-foreground">
                A project is a batch of new reports to link to studies. Create one and upload its reports.
              </p>
              {createProjectButton}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed px-4 py-4 text-sm text-muted-foreground">
              {canCreateHere
                ? "Nothing to curate right now. An admin assigns new batches here."
                : "No projects in this database yet."}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

// The databases, one tab each.
function DatabaseTabs({
  databases,
  selected,
  onSelect,
}: {
  databases: StudyDatabase[];
  selected: string;
  onSelect: (id: string) => void;
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
          {database.name}
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
