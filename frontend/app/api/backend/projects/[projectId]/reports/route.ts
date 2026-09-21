import axios from "axios";
import { NextRequest, NextResponse } from "next/server";
import { getProjectReports } from "@/lib/api/projectApi";
import { getBackendHeaders } from "@/lib/server/backendHeaders";

export async function GET(
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
    const headers = await getBackendHeaders();
    const reports = await getProjectReports(projectId, false, { headers });
    return NextResponse.json(reports);
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      const payload =
        error.response.data ?? { error: "Project reports not found." };
      return NextResponse.json(payload, { status: 404 });
    }

    console.error("Unexpected error while fetching project reports:", error);
    return NextResponse.json(
      { error: "Unexpected error while fetching project reports." },
      { status: 500 }
    );
  }
}
