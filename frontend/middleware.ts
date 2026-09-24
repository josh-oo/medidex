export const runtime = 'nodejs';

import { NextResponse, NextRequest } from "next/server";
import {
  ACCESS_TOKEN_COOKIE,
  ID_TOKEN_COOKIE,
  REFRESH_TOKEN_COOKIE,
  applyTokenCookies,
  clearSessionCookies,
  decodeToken,
  refreshTokens,
  type KeycloakTokens,
} from "./lib/server/keycloak";

export default async function middleware(req: NextRequest) {
  const isPendingApprovalPage = req.nextUrl.pathname.startsWith("/pending-approval");

  const accessToken = req.cookies.get(ACCESS_TOKEN_COOKIE)?.value;
  const refreshToken = req.cookies.get(REFRESH_TOKEN_COOKIE)?.value;

  let payload = accessToken ? decodeToken(accessToken) : null;
  const needsRefresh = !payload || payload.exp * 1000 < Date.now() + 10_000;

  let refreshed: KeycloakTokens | null = null;
  if (needsRefresh) {
    if (!refreshToken) return redirectToLogin(req);
    try {
      refreshed = await refreshTokens(refreshToken);
      payload = decodeToken(refreshed.access_token);
    } catch {
      return redirectToLogin(req);
    }
  }
  if (!payload) return redirectToLogin(req);

  const roles: string[] = payload.roles ?? [];
  const isApproved = roles.includes("APPROVED");

  let res: NextResponse;
  if (isApproved && isPendingApprovalPage) {
    res = NextResponse.redirect(new URL("/", req.url));
  } else if (!isApproved && !isPendingApprovalPage) {
    res = NextResponse.redirect(new URL("/pending-approval", req.url));
  } else if (refreshed) {
    // Continuing to render this same request - propagate the refreshed
    // cookie onto the request too, not just the response, so downstream
    // Server Components see it immediately instead of one request later.
    req.cookies.set(ACCESS_TOKEN_COOKIE, refreshed.access_token);
    if (refreshed.refresh_token) req.cookies.set(REFRESH_TOKEN_COOKIE, refreshed.refresh_token);
    if (refreshed.id_token) req.cookies.set(ID_TOKEN_COOKIE, refreshed.id_token);
    res = NextResponse.next({ request: req });
  } else {
    res = NextResponse.next();
  }

  if (refreshed) {
    applyTokenCookies(res, refreshed);
  }

  return res;
}

function redirectToLogin(req: NextRequest) {
  const res = NextResponse.redirect(new URL("/login", req.url));
  clearSessionCookies(res);
  return res;
}

export const config = {
  matcher: [
    "/api/backend/:path*",
    "/((?!api|_next/static|_next/image|images|favicon.ico|login|register|pending-approval).*)",
  ],
};
