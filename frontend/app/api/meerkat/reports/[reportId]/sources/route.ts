import { NextRequest, NextResponse } from "next/server";
import { getReportSources } from "@/lib/api/reportApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> }
) {
  const { reportId } = await params;

  if (!reportId) {
    return NextResponse.json({ error: "Missing report id." }, { status: 400 });
  }

  try {
    const headers = await getMeerkatHeaders("application/pdf");
    const links = await getReportSources(Number(reportId), {headers});

    return NextResponse.json(links);
  } catch (error) {
    console.error("Unexpected error while fetching report PDF:", error);
    return NextResponse.json(
      { error: "Unexpected error while fetching report PDF." },
      { status: 500 }
    );
  }
}
