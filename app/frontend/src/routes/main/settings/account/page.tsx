import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { DeleteAccountButton } from "@/components/auth/delete-account-panel";
import { SettingsHeader } from "@/components/settings/settings-header";
import { useAuthStore } from "@/hooks/use-auth";
import { getInitials } from "@/lib/utils";

/** The signed-in user's account: who they are signed in as, and deleting it (behind a dialog). */
export default function AccountPage() {
  const user = useAuthStore((s) => s.user);

  return (
    <>
      <SettingsHeader title="Account" />

      {user && (
        <section className="flex items-center gap-4 rounded-2xl border bg-card p-5 shadow-xs">
          <Avatar className="h-12 w-12 rounded-full">
            <AvatarFallback className="rounded-full bg-primary/10 font-medium text-primary">
              {getInitials(user.name)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate font-medium">{user.name}</p>
            <p className="truncate text-sm text-muted-foreground">{user.email}</p>
            {user.isAdmin && <p className="mt-0.5 text-xs text-muted-foreground">Administrator</p>}
          </div>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-destructive">Danger zone</h2>
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-destructive/30 p-5">
          <div className="min-w-0 max-w-xl">
            <p className="font-medium">Delete account</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Removes your name, email address and password, your assignments to updates and your personal settings. This cannot be undone.
            </p>
          </div>
          <DeleteAccountButton
            variant="outline"
            className="gap-2 border-destructive/40 text-destructive hover:bg-destructive/10 hover:text-destructive"
          >
            Delete account…
          </DeleteAccountButton>
        </div>
      </section>
    </>
  );
}
