import { NextRequest, NextResponse } from "next/server";
import { getInterventions } from "@/lib/api/interventionsApi";
import { getBackendHeaders } from "@/lib/server/backendHeaders";

export async function GET(_request: NextRequest) {
  try {
    const headers = await getBackendHeaders();
    const interventions = await getInterventions({ headers });

    return NextResponse.json(interventions);
  } catch (error) {
    console.error("Unexpected error while fetching interventions:", error);
    return NextResponse.json(
      { error: "Unexpected error while fetching interventions." },
      { status: 500 }
    );
  }
}
