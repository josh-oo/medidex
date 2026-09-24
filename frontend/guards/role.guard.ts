import { forbidden } from "next/navigation";
import { getSession } from "../lib/server/session";

export async function adminGuard(): Promise<boolean> {
  const session = await getSession();

  // Check if user is approved AND has admin role
  if (session?.user.isAdmin && session?.user.isApproved) {
    return true;
  }

  forbidden();
}
