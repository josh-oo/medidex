import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { REFRESH_TOKEN_COOKIE, applyTokenCookies, decodeToken, refreshTokens } from "@/lib/server/keycloak";

// Forces a token refresh so a newly granted role (in particular "APPROVED")
// takes effect immediately instead of waiting for the current token to
// expire. Polled by the pending-approval page.
export async function GET() {
  const store = await cookies();
  const refreshToken = store.get(REFRESH_TOKEN_COOKIE)?.value;
  if (!refreshToken) {
    return NextResponse.json({ approved: false });
  }

  try {
    const tokens = await refreshTokens(refreshToken);
    const payload = decodeToken(tokens.access_token);
    const approved = (payload?.roles ?? []).includes("APPROVED");

    const res = NextResponse.json({ approved });
    applyTokenCookies(res, tokens);
    return res;
  } catch {
    return NextResponse.json({ approved: false });
  }
}
