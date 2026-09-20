import { NextRequest, NextResponse } from "next/server";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";
import { assignStudyToReportByReportId, removeStudyFromReportByReportId } from "@/lib/api/reportApi";

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ reportId: string, studyId: string}> }
) {
  const { reportId, studyId} = await params;

  if (typeof reportId === "undefined" || typeof studyId === "undefined") {
    return NextResponse.json(
      { error: "Missing report id or study id." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    await assignStudyToReportByReportId(Number(reportId), Number(studyId), {
      headers,
    });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error(
      "Unexpected error while assigning studies to report:",
      error
    );
    return NextResponse.json(
      { error: "Unexpected error while assigning studies to report." },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ reportId: string, studyId : string}> }
) {
  const {reportId, studyId } = await params;

  if (typeof reportId === "undefined" || typeof studyId === "undefined") {
    return NextResponse.json(
      { error: "Missing report id or study id." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    await removeStudyFromReportByReportId(Number(reportId), Number(studyId), { headers });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error(
      "Unexpected error while removing studies from report:",
      error
    );
    return NextResponse.json(
      { error: "Unexpected error while removing studies from report." },
      { status: 500 }
    );
  }
}