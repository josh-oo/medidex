import { AppHeader } from "@/components/header/app-header";
import { AuthSync } from "@/components/auth/auth-sync";
import { getSession } from "@/lib/server/session";

export default async function Layout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const session = await getSession();

  return (
    <div className="h-full overflow-hidden">
      {session && (
        <AuthSync
          accessToken={session.accessToken}
          refreshToken={session.refreshToken}
          idToken={session.idToken}
        />
      )}
      <AppHeader />
      <main className="pt-14 h-full overflow-hidden flex flex-col">
        {children}
      </main>
    </div>
  );
}
