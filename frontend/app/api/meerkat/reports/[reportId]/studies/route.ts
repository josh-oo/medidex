import { NextRequest, NextResponse } from "next/server";
import { assignNewStudyToReportByReportId, getStudiesByReportId } from "@/lib/api/reportApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";
import { StudyDto } from "@/types/apiDTOs";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> }
) {
  const { reportId } = await params;

  if (!reportId) {
    return NextResponse.json(
      { error: "Missing report id." },
      { status: 400 }
    );
  }

  const searchParams = request.nextUrl.searchParams;
  const date_from = searchParams.get("date_from");
  const date_to = searchParams.get("date_to");

  try {
    const headers = await getMeerkatHeaders();
    const studies = await getStudiesByReportId(Number(reportId), {
      date_from: date_from || undefined,
      date_to: date_to || undefined,
    }, { headers });

    return NextResponse.json(studies);
  } catch (error) {
    console.error(
      `Unexpected error while fetching studies for report ${reportId}:`,
      error
    );
    return NextResponse.json(
      { error: "Unexpected error while fetching studies for report." },
      { status: 500 }
    );
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> }
) {
  const { reportId } = await params;

  if (!reportId) {
    return NextResponse.json(
      { error: "Missing report id." },
      { status: 400 }
    );
  }

  let studyPayload: StudyDto | undefined;
  try {
    studyPayload = await request.json();
  } catch (error) {
    console.error("Invalid study payload.", error);
    return NextResponse.json(
      { error: "Invalid study payload." },
      { status: 400 }
    );
  }

  if (!studyPayload) {
    return NextResponse.json(
      { error: "Missing study payload." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    const createdStudy = await assignNewStudyToReportByReportId(
      Number(reportId),
      studyPayload,
      { headers }
    );

    return NextResponse.json(
      createdStudy ?? { success: true },
      { status: 200 }
    );
  } catch (error) {
    console.error(
      `Unexpected error while creating a study for report ${reportId}:`,
      error
    );
    return NextResponse.json(
      { error: "Unexpected error while assigning study to report." },
      { status: 500 }
    );
  }
}
