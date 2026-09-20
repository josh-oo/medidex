import { NextRequest, NextResponse } from "next/server";
import { getStudyById } from "@/lib/api/studiesApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function GET(_request: NextRequest, { params }: { params: Promise<{ studyId: string }> }) {
  
  const { studyId } = await params;

  if (!studyId) {
    return NextResponse.json(
      { error: "Missing study id." },
      { status: 400 }
    );
  }

  const studyIdNumber = Number(studyId);
  if (Number.isNaN(studyIdNumber)) {
    return NextResponse.json(
      { error: "Invalid study id." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    const study = await getStudyById(studyIdNumber, { headers });
    return NextResponse.json(study, { status: 200 });
  } catch (error) {
    const status =
      typeof error === "object" &&
      error !== null &&
      "response" in error &&
      typeof (error as { response?: { status?: number } }).response?.status === "number"
        ? (error as { response?: { status?: number } }).response?.status
        : undefined;

    if (status === 404) {
      return NextResponse.json(
        { error: `Study ${studyId} not found.` },
        { status: 404 }
      );
    }

    console.error(`Unexpected error while fetching study ${studyId}:`, error);
    return NextResponse.json(
      { error: "Unexpected error while fetching study." },
      { status: 500 }
    );
  }
}