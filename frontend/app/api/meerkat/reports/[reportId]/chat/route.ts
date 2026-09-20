import { NextRequest, NextResponse } from "next/server";
import { deleteReportChat, getReportChat, postReportChat } from "@/lib/api/reportApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> }
) {
  const { reportId } = await params;

  if (!reportId) {
    return NextResponse.json({ error: "Missing report id." }, { status: 400 });
  }

  const id = Number(reportId);
  if (Number.isNaN(id)) {
    return NextResponse.json({ error: "Invalid report id." }, { status: 400 });
  }

  try {
    const headers = await getMeerkatHeaders();
    const chat = await getReportChat(id, { headers });

    return NextResponse.json(chat);
  } catch (error) {
    console.error(`Unexpected error while fetching chat for report ${reportId}:`, error);
    return NextResponse.json(
      { error: "Unexpected error while fetching report chat." },
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
    return NextResponse.json({ error: "Missing report id." }, { status: 400 });
  }

  const id = Number(reportId);
  if (Number.isNaN(id)) {
    return NextResponse.json({ error: "Invalid report id." }, { status: 400 });
  }

  let message: string;
  try {
    message = await request.text();
  } catch {
    return NextResponse.json({ error: "Invalid request body." }, { status: 400 });
  }

  try {
    const headers = await getMeerkatHeaders();
    const chat = await postReportChat(id, message, {
      headers: {
        ...headers,
        "Content-Type": "text/plain",
      },
    });

    return NextResponse.json(chat);
  } catch (error) {
    console.error(`Unexpected error while posting chat message for report ${reportId}:`, error);
    return NextResponse.json(
      { error: "Unexpected error while posting report chat message." },
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

  const id = Number(reportId);
  if (Number.isNaN(id)) {
    return NextResponse.json({ error: "Invalid report id." }, { status: 400 });
  }

  try {
    const headers = await getMeerkatHeaders();
    await deleteReportChat(id, { headers });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error(`Unexpected error while deleting chat for report ${reportId}:`, error);
    return NextResponse.json(
      { error: "Unexpected error while deleting report chat." },
      { status: 500 }
    );
  }
}
