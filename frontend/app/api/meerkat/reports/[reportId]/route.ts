import { NextRequest, NextResponse } from "next/server";
import { deleteReportById } from "@/lib/api/reportApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> }
) {
  const { reportId } = await params;

  if (!reportId) {
    return NextResponse.json(
      { error: "Missing report id." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    await deleteReportById(Number(reportId), { headers });
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error(`Unexpected error while deleting report ${reportId}:`, error);
    return NextResponse.json(
      { error: "Unexpected error while deleting report." },
      { status: 500 }
    );
  }
}
