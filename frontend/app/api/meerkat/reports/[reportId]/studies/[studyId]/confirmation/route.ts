import { NextRequest, NextResponse } from "next/server";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";
import {
  confirmStudyForReportByReportId,
  unconfirmStudyForReportByReportId,
} from "@/lib/api/reportApi";

export async function PUT(
  _request: NextRequest,
  { params }: { params: Promise<{ reportId: string; studyId: string }> }
) {
  const { reportId, studyId } = await params;

  if (typeof reportId === "undefined" || typeof studyId === "undefined") {
    return NextResponse.json(
      { error: "Missing report id or study id." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    await confirmStudyForReportByReportId(Number(reportId), Number(studyId), {
      headers,
    });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error(
      "Unexpected error while confirming study for report:",
      error
    );
    return NextResponse.json(
      { error: "Unexpected error while confirming study for report." },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ reportId: string; studyId: string }> }
) {
  const { reportId, studyId } = await params;

  if (typeof reportId === "undefined" || typeof studyId === "undefined") {
    return NextResponse.json(
      { error: "Missing report id or study id." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    await unconfirmStudyForReportByReportId(Number(reportId), Number(studyId), {
      headers,
    });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error(
      "Unexpected error while removing study confirmation for report:",
      error
    );
    return NextResponse.json(
      { error: "Unexpected error while removing study confirmation for report." },
      { status: 500 }
    );
  }
}
