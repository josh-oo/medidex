import { Outlet } from "react-router-dom";
import { AppHeader } from "@/components/header/app-header";
import { AuthGuard } from "@/components/auth/auth-guard";

export default function Layout() {
  return (
    <AuthGuard>
      <div className="h-full overflow-hidden">
        <AppHeader />
        <main className="pt-14 h-full overflow-hidden flex flex-col">
          <Outlet />
        </main>
      </div>
    </AuthGuard>
  );
}
