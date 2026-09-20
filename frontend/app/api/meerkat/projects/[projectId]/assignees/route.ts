import { NextRequest, NextResponse } from "next/server";
import { assignUserToProject } from "@/lib/api/projectApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ projectId: string }> }
) {
  const resolvedParams = await params;
  const { projectId } = resolvedParams;

  if (!projectId) {
    return NextResponse.json({ detail: "projectId is required" }, { status: 400 });
  }

  let userId: string;
  try {
    userId = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  if (typeof userId !== "string" || userId.trim().length === 0) {
    return NextResponse.json({ detail: "userId must be a non-empty string" }, { status: 400 });
  }

  try {
    const headers = await getMeerkatHeaders();
    const assignee = await assignUserToProject(projectId, userId.trim(), { headers });
    return NextResponse.json(assignee, { status: 201 });
  } catch (error) {
    console.error(`Failed to assign user ${userId} to project ${projectId}:`, error);
    const detail =
      error instanceof Error && error.message
        ? error.message
        : "Failed to assign user to project";
    const status = (error as { status?: number })?.status;
    return NextResponse.json(
      { detail },
      { status: typeof status === "number" ? status : 500 }
    );
  }
}
