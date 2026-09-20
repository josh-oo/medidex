import { NextRequest, NextResponse } from "next/server";
import {
  deleteReportFlagByReportId,
  getReportFlagByReportId,
  upsertReportFlagByReportId,
} from "@/lib/api/reportApi";
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
    const headers = await getMeerkatHeaders();
    const flag = await getReportFlagByReportId(Number(reportId), { headers });
    return NextResponse.json(flag);
  } catch (error) {
    console.error("Unexpected error while fetching report flag:", error);
    return NextResponse.json(
      { error: "Unexpected error while fetching report flag." },
      { status: 500 }
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> }
) {
  const { reportId } = await params;

  if (!reportId) {
    return NextResponse.json({ error: "Missing report id." }, { status: 400 });
  }

  try {
    const body = await request.json();
    const message = typeof body?.message === "string" ? body.message.trim() : "";
    const isPublic = Boolean(body?.public);

    if (!message) {
      return NextResponse.json(
        { error: "Missing flag message." },
        { status: 400 }
      );
    }

    const headers = await getMeerkatHeaders();
    const flag = await upsertReportFlagByReportId(
      Number(reportId),
      { message, public: isPublic },
      { headers }
    );

    return NextResponse.json(flag);
  } catch (error) {
    console.error("Unexpected error while upserting report flag:", error);
    return NextResponse.json(
      { error: "Unexpected error while upserting report flag." },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> }
) {
  const { reportId } = await params;

  if (!reportId) {
    return NextResponse.json({ error: "Missing report id." }, { status: 400 });
  }

  try {
    const headers = await getMeerkatHeaders();
    await deleteReportFlagByReportId(Number(reportId), { headers });
    return new NextResponse(null, { status: 204 });
  } catch (error) {
    console.error("Unexpected error while deleting report flag:", error);
    return NextResponse.json(
      { error: "Unexpected error while deleting report flag." },
      { status: 500 }
    );
  }
}
