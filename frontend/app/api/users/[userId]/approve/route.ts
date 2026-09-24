export const runtime = 'nodejs';

import { NextRequest, NextResponse } from "next/server";
import { getSession } from "@/lib/server/session";
import { approveUser } from "@/lib/server/keycloakAdmin";

export async function PATCH(
  _request: NextRequest,
  { params }: { params: Promise<{ userId: string }> }
) {
  const { userId } = await params;

  const session = await getSession();
  if (!session?.user?.isAdmin) {
    return NextResponse.json(
      { error: "Unauthorized" },
      { status: 403 }
    );
  }

  try {
    await approveUser(userId);
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error approving user:", error);
    return NextResponse.json(
      { error: "Failed to approve user" },
      { status: 500 }
    );
  }
}
