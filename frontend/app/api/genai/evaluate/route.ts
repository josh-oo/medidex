
import { NextResponse } from "next/server";
import { evaluateStudies } from "@/lib/api/genaiApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";
import type { EvaluateRequest } from "@/types/apiDTOs";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    // Basic validation for EvaluateRequest shape
    if (!body || typeof body !== "object" || !body.report || !body.studies) {
      return NextResponse.json(
        { error: "Missing or invalid request body." },
        { status: 400 }
      );
    }

    const headers = await getMeerkatHeaders();
    const result = await evaluateStudies(body as EvaluateRequest, { headers });
    return NextResponse.json(result, { status: 201 });
  } catch (error) {
    console.error(`Failed to evaluate studies:`, error);
    const detail =
      error instanceof Error && error.message
        ? error.message
        : "Failed to evaluate studies";
    const status = (error as { status?: number })?.status;
    return NextResponse.json(
      { detail },
      { status: typeof status === "number" ? status : 500 }
    );
  }
}