import { NextRequest, NextResponse } from "next/server";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";
import { getSimilarTagsByReportId } from "@/lib/api/reportApi";

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> }
) {
  const { reportId } = await params;
  if (typeof reportId === "undefined") {
    return NextResponse.json(
      { error: "Missing report id." },
      { status: 400 }
    );
  }
  
  try {
    const headers = await getMeerkatHeaders();
    const similarTags = await getSimilarTagsByReportId(
      Number(reportId),
      { aspect: "interventions", k: 10 },
      { headers }
    );

    return NextResponse.json(similarTags);
  } catch (error) {
    console.error(
      "Unexpected error while fetching similar tags:",
      error
    );
    return NextResponse.json(
      { error: "Unexpected error while fetching similar tags." },
      { status: 500 }
    );
  }
}