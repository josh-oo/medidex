export const runtime = 'nodejs';

import { NextRequest, NextResponse } from "next/server";
import prisma from "@/lib/db";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";
import { Role } from "@/enums/role.enum";

export async function PATCH(
  _request: NextRequest,
  { params }: { params: Promise<{ userId: string }> }
) {
  const { userId } = await params;

  // Check if user is admin
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  const isAdmin = session?.user?.roles?.includes(Role.ADMIN);

  if (!isAdmin) {
    return NextResponse.json(
      { error: "Unauthorized" },
      { status: 403 }
    );
  }

  try {
    const updatedUser = await prisma.user.update({
      where: { id: userId },
      data: { isApproved: true },
    });

    // Delete all sessions for this user to force re-login with updated approval status
    await prisma.session.deleteMany({
      where: { userId: userId }
    });

    return NextResponse.json({ success: true, user: updatedUser });
  } catch (error) {
    console.error("Error approving user:", error);
    return NextResponse.json(
      { error: "Failed to approve user" },
      { status: 500 }
    );
  }
}