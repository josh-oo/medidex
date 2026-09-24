import { getSession } from "@/lib/server/session";
import { AppHeaderClient } from "./app-header-client";

export async function AppHeader() {
  const session = await getSession();

  const sessionUser = session?.user;

  const user = sessionUser
    ? {
        name: sessionUser.name || "User",
        email: sessionUser.email || "",
        avatar: "",
        isAdmin: sessionUser.isAdmin,
      }
    : null;

  return <AppHeaderClient user={user} />;
}
