import { DeleteAccountPanel } from "@/components/auth/delete-account-panel";

export default function AccountPage() {
  return (
    // The app layout clips overflow, so the page scrolls itself.
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-6 px-4 pb-10 pt-4 md:px-8 md:pt-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Delete account</h1>
        </div>
        <div className="rounded-2xl border bg-card p-5 shadow-xs">
          <DeleteAccountPanel />
        </div>
      </div>
    </div>
  );
}
