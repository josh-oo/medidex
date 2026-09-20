export const runtime = 'nodejs';

import { NextRequest, NextResponse } from "next/server";
import { auth } from "./lib/auth";
import { headers } from "next/headers";

export async function middleware(request: NextRequest) {
  const stage = process.env.STAGE!;
  const cookie = request.cookies.get(
    stage === "local"
      ? "better-auth.session_token"
      : "__Secure-better-auth.session_token"
  );

  if (!cookie || !cookie.value) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });

    const isApproved = (session as any)?.user.isApproved ?? false;
    const isPendingApprovalPage = request.nextUrl.pathname.startsWith("/pending-approval");

    // If user is approved but on pending-approval page, redirect to home
    if (isApproved && isPendingApprovalPage) {
      return NextResponse.redirect(new URL("/", request.url));
    }

    // If user is not approved and not on pending-approval page, redirect to pending
    if (session?.user && !isApproved && !isPendingApprovalPage) {
      return NextResponse.redirect(new URL("/pending-approval", request.url));
    }
  } catch (error) {
    console.error("Error checking user approval:", error);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/api/meerkat/:path*",
    "/((?!api|_next/static|_next/image|images|favicon.ico|login|register|pending-approval).*)",
  ],
};
