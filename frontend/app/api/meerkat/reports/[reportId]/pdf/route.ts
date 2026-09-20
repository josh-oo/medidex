import { NextRequest, NextResponse } from "next/server";
import { deleteReportPdf, getReportPdf, uploadPdf } from "@/lib/api/reportApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

function sanitizePdfFilename(value: string) {
  return value
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

export async function POST(request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> }
) {
  const { reportId } = await params;
  let file: File | null = null;
  let formData = null;

  // Check if the request is multipart/form-data
  const contentType = request.headers.get("content-type") || "";
  console.log("Hit 1");
  if (contentType.includes("multipart/form-data")) {
    try {
      formData = await request.formData();
      const uploaded = formData.get("file");
      file = uploaded instanceof File ? uploaded : null;
      console.log("Hit 2");
    } catch (e) {
      console.error("Failed to parse form data", e);
    }
  } else {
    // Handle other content types if needed
    console.warn("Request is not multipart/form-data");
  }

  console.log("Hit 3");

  try {
    const headers = await getMeerkatHeaders();
    const result = await uploadPdf(Number(reportId), file, { headers });
    return NextResponse.json({ result });
  } catch (error) {
    console.error("Unexpected error while uploading pdf:", error);
    return NextResponse.json(
      { error: "Unexpected error while uploading pdf." },
      { status: 500 }
    );
  }
}

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> }
) {
  const { reportId } = await params;
  const filename = sanitizePdfFilename(
    _request.nextUrl.searchParams.get("filename") || `report-${reportId}.pdf`
  ) || `report-${reportId}.pdf`;

  if (!reportId) {
    return NextResponse.json({ error: "Missing report id." }, { status: 400 });
  }

  try {
    const headers = await getMeerkatHeaders("application/pdf");
    const pdfBuffer = await getReportPdf(Number(reportId), {
      headers,
      responseType: "arraybuffer",
    });

    return new NextResponse(pdfBuffer, {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": `inline; filename="${filename}"`,
      },
    });
  } catch (error: any) {
    // Check for 404 error (Not Found)
    const status = error?.response?.status || error?.status;
    if (status === 404) {
      // Return a centered HTML dummy page
      const html = `<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\"><title>PDF Not Found</title></head><body style=\"display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;\"><div style=\"text-align:center;\"><h2 style=\"margin-bottom:0.5em;\">PDF Not Found</h2><p style=\"margin-top:0;\">The requested report PDF is not available yet.</p></div></body></html>`;
      return new NextResponse(html, {
        status: 404,
        headers: {
          "Content-Type": "text/html; charset=utf-8",
        },
      });
    }
    console.error("Unexpected error while fetching report PDF:", error);
    return NextResponse.json(
      { error: "Unexpected error while fetching report PDF." },
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
    await deleteReportPdf(Number(reportId), { headers });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Unexpected error while deleting report PDF:", error);
    return NextResponse.json(
      { error: "Unexpected error while deleting report PDF." },
      { status: 500 }
    );
  }
}


