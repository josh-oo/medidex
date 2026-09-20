import { NextRequest, NextResponse } from "next/server";
import { createStudy, searchStudies } from "@/lib/api/studiesApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";
import { StudyCreateDto, StudyDto } from "@/types/apiDTOs";

// The backend rejects shorter queries with a 422.
const MIN_QUERY_LENGTH = 3;

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("q")?.trim() ?? "";

  if (query.length < MIN_QUERY_LENGTH) {
    return NextResponse.json(
      { error: `Search query must be at least ${MIN_QUERY_LENGTH} characters.` },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    const studies = await searchStudies(query, { headers });

    return NextResponse.json(studies);
  } catch (error) {
    console.error("Unexpected error while searching studies:", error);
    return NextResponse.json(
      { error: "Unexpected error while searching studies." },
      { status: 500 }
    );
  }
}

export async function PUT(request: NextRequest) {
  let body: Partial<StudyDto>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "Invalid JSON body." },
      { status: 400 }
    );
  }

  const requiredFields: Array<keyof StudyDto> = [
    "shortName",
    "status",
    "comparison",
    "countries",
    "duration",
    "numberParticipants",
  ];

  const missing = requiredFields.filter((field) => {
    const value = body?.[field];
    if (field === "countries") {
      return !Array.isArray(value) || value.length === 0;
    }
    if (field === "numberParticipants") {
      return typeof value !== "number" || Number.isNaN(value);
    }
    return typeof value !== "string" || value.trim().length === 0;
  });

  if (missing.length > 0) {
    return NextResponse.json(
      { error: `Missing required fields: ${missing.join(", ")}` },
      { status: 400 }
    );
  }

  const payload: StudyCreateDto = {
    shortName: body.shortName!.trim(),
    status: body.status!.trim(),
    comparison: body.comparison!.trim(),
    duration: body.duration!.trim(),
    countries: Array.isArray(body.countries)
      ? body.countries
          .map((country) => (typeof country === "string" ? country.trim() : ""))
          .filter(Boolean)
      : [],
    numberParticipants: body.numberParticipants ?? null,
    trialId: null, //TODO
  };

  if (payload.countries.length === 0) {
    return NextResponse.json(
      { error: "countries must contain at least one entry." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    const createdStudy = await createStudy(payload, { headers });

    return NextResponse.json(createdStudy, { status: 200 });
  } catch (error) {
    console.error("Unexpected error while creating study:", error);
    return NextResponse.json(
      { error: "Unexpected error while creating study." },
      { status: 500 }
    );
  }
}
