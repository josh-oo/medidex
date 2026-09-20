import { headers } from "next/headers";
import { auth } from "../auth";

export async function getMeerkatHeaders(accept: string = "application/json") {
  const requestHeaders = await headers();
  const token = await auth.api.getToken({
    headers: requestHeaders,
  });

  return {
    Authorization: `Bearer ${token.token}`,
    Accept: accept,
  } as const;
}
