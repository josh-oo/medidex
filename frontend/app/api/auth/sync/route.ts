import { NextRequest, NextResponse } from "next/server";
import { applyTokenCookies, clearSessionCookies } from "@/lib/server/keycloak";

// Called by the browser's keycloak-js instance right after it signs in or
// refreshes a token, so the httpOnly cookies stay in sync with whatever
// Keycloak just issued. This endpoint trusts the tokens it's handed (it's a
// same-origin call from our own client code) - the real security boundary is
// the FastAPI backend independently verifying the token's signature on every
// request, regardless of how it arrived in the cookie.
export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => null);
  if (!body?.accessToken) {
    return NextResponse.json({ error: "Missing accessToken" }, { status: 400 });
  }

  const res = NextResponse.json({ ok: true });
  applyTokenCookies(res, {
    access_token: body.accessToken,
    refresh_token: body.refreshToken,
    id_token: body.idToken,
  });
  return res;
}

export async function DELETE() {
  const res = NextResponse.json({ ok: true });
  clearSessionCookies(res);
  return res;
}
