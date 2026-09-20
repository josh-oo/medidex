import { NextRequest, NextResponse } from "next/server";
import { getPersonsForStudy } from "@/lib/api/studiesApi";
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
    const persons = await getPersonsForStudy(id, { headers });


    return NextResponse.json(persons);
  } catch (error) {
    console.error(`Unexpected error while fetching persons for study ${studyId}:`, error);
    return NextResponse.json(
      { error: "Unexpected error while fetching study persons." },
      { status: 500 }
    );
  }
}
