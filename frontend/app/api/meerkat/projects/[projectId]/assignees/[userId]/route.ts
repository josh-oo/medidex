import { NextResponse } from "next/server";
import { removeUserFromProject } from "@/lib/api/projectApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ projectId: string; userId: string }> }
) {
  const { projectId, userId } = await params;

  if (!projectId || !userId) {
    return NextResponse.json(
      { detail: "Both projectId and userId are required" },
      { status: 400 }
    );
  }

  if (typeof userId !== "string" || userId.trim().length === 0) {
    return NextResponse.json(
      { detail: "userId must be a non-empty string" },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    await removeUserFromProject(projectId, userId.trim(), { headers });
    return new Response(null, { status: 204 });
  } catch (error) {
    console.error(`Failed to remove user ${userId} from project ${projectId}:`, error);
    const detail =
      error instanceof Error && error.message
        ? error.message
        : "Failed to remove user from project";
    const status = (error as { response?: { status?: number } })?.response?.status;
    return NextResponse.json(
      { detail },
      { status: typeof status === "number" ? status : 500 }
    );
  }
}
