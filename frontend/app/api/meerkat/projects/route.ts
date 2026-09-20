import { NextResponse, NextRequest } from "next/server";
import { getProjects, createProject } from "@/lib/api/projectApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function POST(request: NextRequest) {
  const formData = await request.formData();
  const file = formData.get("file");
  const projectName = formData.get("projectName");

  if (!file || !(file instanceof File)) {
    return NextResponse.json(
      { error: "Missing file in upload request." },
      { status: 400 }
    );
  }

  if (!projectName || typeof projectName !== "string") {
    return NextResponse.json(
      { error: "Missing project_name in upload request." },
      { status: 400 }
    );
  }

  try {
    const headers = await getMeerkatHeaders();
    const projectId = await createProject(file, projectName, { headers });
    return NextResponse.json({ projectId });
  } catch (error) {
    console.error("Unexpected error while creating project:", error);
    return NextResponse.json(
      { error: "Unexpected error while creating project." },
      { status: 500 }
    );
  }
}

export async function GET() {
  try {
    const headers = await getMeerkatHeaders();
    const projects = await getProjects({
      headers,
    });

    return NextResponse.json(projects);
  } catch (error) {
    console.error("Unexpected error while fetching Meerkat projects:", error);
    return NextResponse.json(
      { error: "Unexpected error while fetching projects." },
      { status: 500 }
    );
  }
}
