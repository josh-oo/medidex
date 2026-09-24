import { getSession } from "./session";

export async function getBackendHeaders(accept: string = "application/json") {
  const session = await getSession();

  return {
    Authorization: `Bearer ${session?.accessToken ?? ""}`,
    Accept: accept,
  } as const;
}
