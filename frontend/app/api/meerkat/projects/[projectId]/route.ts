import { NextRequest, NextResponse } from "next/server";
import { deleteProjectById } from "@/lib/api/projectApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ projectId: string }> }
) {
  const { projectId } = await params;

  if (!projectId) {
    return NextResponse.json(
      { error: "Missing project id." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    await deleteProjectById(projectId, { headers });
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Unexpected error while deleting project:", error);
    return NextResponse.json(
      { error: "Unexpected error while deleting project." },
      { status: 500 }
    );
  }
}
