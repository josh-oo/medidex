import { useEffect, useState } from "react";
import { AlertTriangle, Ban, UserX } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { PageLink } from "@/lib/page-transition";
import { getKeycloak } from "@/lib/client/keycloak";
import { deleteAccount, getAccountDeletion, type AccountDeletion } from "@/lib/api/accountApi";

interface DeleteAccountPanelProps {
  /** Runs before anything is loaded, e.g. to restore the Keycloak session on a page outside the app layout. */
  prepare?: () => Promise<unknown>;
  /** Whether the user can reach the pages of the app (links to the Curation page and User management). */
  inApp?: boolean;
}

function errorDetail(error: unknown): string | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === "string" ? detail : null;
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/**
 * Deleting the account of the signed-in user: what stands in the way (what they own, being the only administrator),
 * what they have not handed in, and the deletion itself, confirmed with their email address.
 */
export function DeleteAccountPanel({ prepare, inApp = true }: DeleteAccountPanelProps) {
  const [deletion, setDeletion] = useState<AccountDeletion | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [email, setEmail] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await prepare?.();
        const status = await getAccountDeletion();
        if (cancelled) return;
        setEmail((getKeycloak().tokenParsed as { email?: string } | undefined)?.email ?? "");
        setDeletion(status);
      } catch (error) {
        console.error("Failed to load what stands in the way of deleting the account:", error);
        if (!cancelled) setLoadFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [prepare]);

  if (loadFailed) {
    return <p className="text-sm text-destructive">Could not load your account. Please try again later.</p>;
  }
  if (deletion === null) {
    return (
      <div className="flex justify-center py-6">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  const owns = deletion.ownedDatabases.length > 0;
  const blocked = owns || deletion.onlyAdmin;
  const confirmed = email !== "" && confirmation.trim().toLowerCase() === email.toLowerCase();

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteAccount();
    } catch (error) {
      toast.error(errorDetail(error) ?? "Failed to delete your account");
      setDeleting(false);
      return;
    }
    // The user and their sessions are gone in Keycloak: drop the tokens here and start over at the sign-in.
    getKeycloak().clearToken();
    window.location.replace(`${window.location.origin}/login`);
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2 text-sm text-muted-foreground">
        <p>
          Deleting your account removes your name, email address and password, your assignments to updates and your
          personal settings. It cannot be undone, and you are signed out right away.
        </p>
        <p>
          What you contributed to the shared database (links, studies, flags) stays, but no longer shows your name.
        </p>
      </div>

      {blocked && (
        <div role="alert" className="space-y-2 rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm">
          <p className="flex items-center gap-2 font-medium text-destructive">
            <Ban className="h-4 w-4 shrink-0" aria-hidden />
            You cannot delete your account yet
          </p>
          {owns && (
            <>
              <p>You own these study databases. Transfer their ownership to another user first:</p>
              <ul className="list-disc space-y-0.5 pl-5">
                {deletion.ownedDatabases.map((database) => (
                  <li key={database.databaseId}>
                    <span className="font-medium">{database.name}</span>
                  </li>
                ))}
              </ul>
              <p className="text-muted-foreground">
                The ownership is transferred from the card of the database on the{" "}
                {inApp ? (
                  <PageLink to="/curation" className="underline underline-offset-4 hover:text-foreground">
                    Curation page
                  </PageLink>
                ) : (
                  "Curation page"
                )}
                .
              </p>
            </>
          )}
          {deletion.onlyAdmin && (
            <p>
              You are the only administrator. Make another user an administrator first
              {inApp ? (
                <>
                  {" "}
                  (
                  <PageLink to="/user-management" className="underline underline-offset-4 hover:text-foreground">
                    User management
                  </PageLink>
                  )
                </>
              ) : null}
              .
            </p>
          )}
        </div>
      )}

      {deletion.openTasks.length > 0 && (
        <div className="space-y-2 rounded-xl border border-amber-500/40 bg-amber-500/5 p-4 text-sm">
          <p className="flex items-center gap-2 font-medium text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
            You have work that is not handed in
          </p>
          <ul className="list-disc space-y-0.5 pl-5">
            {deletion.openTasks.map((task) => (
              <li key={task.projectId}>
                <span className="font-medium">{task.name}</span>:{" "}
                {[
                  task.numberReportsUncommitted > 0 && `${plural(task.numberReportsUncommitted, "report")} done but not committed`,
                  task.numberReportsOpen > 0 && `${plural(task.numberReportsOpen, "report")} not done yet`,
                ]
                  .filter(Boolean)
                  .join(", ") || "not committed"}
              </li>
            ))}
          </ul>
          <p className="text-muted-foreground">
            Your assignments end with your account: the owner of the update no longer waits for you, and what you did
            not commit does not count. Commit your work first if it should.
          </p>
        </div>
      )}

      <div className="space-y-3">
        <Label htmlFor="delete-account-confirmation">
          To confirm, type your email address <span className="font-mono">{email}</span>
        </Label>
        <Input
          id="delete-account-confirmation"
          autoComplete="off"
          value={confirmation}
          onChange={(event) => setConfirmation(event.target.value)}
          disabled={blocked || deleting}
        />
        <Button variant="destructive" className="gap-2" disabled={blocked || !confirmed || deleting} onClick={handleDelete}>
          {deleting ? <Spinner className="h-4 w-4" /> : <UserX className="h-4 w-4" />}
          Delete my account
        </Button>
      </div>
    </div>
  );
}
