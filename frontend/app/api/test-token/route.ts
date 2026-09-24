import { NextResponse } from "next/server";
import { getSession } from "@/lib/server/session";

export async function GET() {
  const session = await getSession();
  return NextResponse.json({ access_token: session?.accessToken ?? null });
}
