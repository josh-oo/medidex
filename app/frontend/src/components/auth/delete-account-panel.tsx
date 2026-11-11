import { useRef, useState, type ComponentProps } from "react";
import { AlertTriangle, Ban, UserX } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { PageLink } from "@/lib/page-transition";
import { getKeycloak } from "@/lib/client/keycloak";
import { deleteAccount, getAccountDeletion, type AccountDeletion } from "@/lib/api/accountApi";

/** What the panel shows: what stands in the way of the deletion, and the email address that confirms it. */
export interface LoadedAccountDeletion {
  deletion: AccountDeletion;
  email: string;
}

/**
 * Loads what the panel shows. The caller loads it before showing the panel, so the dialog opens at its final size.
 * `prepare` runs first, e.g. to restore the Keycloak session on a page outside the app layout.
 */
export async function loadAccountDeletion(prepare?: () => Promise<unknown>): Promise<LoadedAccountDeletion> {
  await prepare?.();
  const deletion = await getAccountDeletion();
  return { deletion, email: (getKeycloak().tokenParsed as { email?: string } | undefined)?.email ?? "" };
}

interface DeleteAccountPanelProps extends LoadedAccountDeletion {
  /** Whether the user can reach the pages of the app (links to the Curation page and the users in the settings). */
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
export function DeleteAccountPanel({ deletion, email, inApp = true }: DeleteAccountPanelProps) {
  const [confirmation, setConfirmation] = useState("");
  const [deleting, setDeleting] = useState(false);

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
                  <PageLink to="/settings/users" className="underline underline-offset-4 hover:text-foreground">
                    Settings › Users
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

// How long the load may take before the button shows that it is loading.
const SPINNER_DELAY_MS = 400;

type DeleteAccountButtonProps = Omit<ComponentProps<typeof Button>, "onClick"> & {
  prepare?: () => Promise<unknown>;
  inApp?: boolean;
};

/**
 * A button that opens the deletion in a dialog. It loads what the panel shows first (spinning meanwhile), so the dialog
 * does not open small and then grow, which would move it as it stays centred.
 */
export function DeleteAccountButton({ prepare, inApp = true, children, disabled, ...buttonProps }: DeleteAccountButtonProps) {
  const [loaded, setLoaded] = useState<LoadedAccountDeletion | null>(null);
  const [open, setOpen] = useState(false);
  // A quick load changes nothing on the button (a spinner shown for a moment flickers); a slow one spins and disables it.
  const loading = useRef(false);
  const [slow, setSlow] = useState(false);
  // Counts the openings: each starts with a fresh panel (and confirmation).
  const [opening, setOpening] = useState(0);

  const openDialog = async () => {
    if (loading.current) return;
    loading.current = true;
    const slowTimer = window.setTimeout(() => setSlow(true), SPINNER_DELAY_MS);
    try {
      setLoaded(await loadAccountDeletion(prepare));
      setOpening((count) => count + 1);
      setOpen(true);
    } catch (error) {
      console.error("Failed to load what stands in the way of deleting the account:", error);
      toast.error("Could not load your account. Please try again later.");
    } finally {
      window.clearTimeout(slowTimer);
      loading.current = false;
      setSlow(false);
    }
  };

  return (
    <>
      <Button {...buttonProps} disabled={disabled || slow} aria-busy={slow || undefined} onClick={() => void openDialog()}>
        {slow ? <Spinner className="h-4 w-4" /> : <UserX className="h-4 w-4" />}
        {children}
      </Button>
      {/* The content stays while the dialog closes. */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Delete account</DialogTitle>
          </DialogHeader>
          {loaded && <DeleteAccountPanel key={opening} {...loaded} inApp={inApp} />}
        </DialogContent>
      </Dialog>
    </>
  );
}
