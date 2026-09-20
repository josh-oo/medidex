import { NextRequest, NextResponse } from "next/server";
import { getOutcomesForStudy } from "@/lib/api/studiesApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ studyId: string }> }
) {
  const { studyId } = await params;

  if (!studyId) {
    return NextResponse.json(
      { error: "Missing study id." },
      { status: 400 }
    );
  }

  const id = Number(studyId);
  if (Number.isNaN(id)) {
    return NextResponse.json(
      { error: "Invalid study id." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    const outcomes = await getOutcomesForStudy(id, { headers });


    return NextResponse.json(outcomes);
  } catch (error) {
    console.error(`Unexpected error while fetching outcomes for study ${studyId}:`, error);
    return NextResponse.json(
      { error: "Unexpected error while fetching study outcomes." },
      { status: 500 }
    );
  }
}
