import { NextRequest, NextResponse } from "next/server";
import { headers } from "next/headers";
import { auth } from "../../../lib/auth";

export async function GET(request: NextRequest) {
  const requestHeaders = await headers();
  const token = await auth.api.getToken({
    headers: requestHeaders,
  });
  return NextResponse.json(token);
}
