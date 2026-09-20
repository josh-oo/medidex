import { NextResponse } from "next/server";
import { fetchDefaultPrompts } from "@/lib/api/genaiApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function GET() {

  try {
      const headers = await getMeerkatHeaders();
      const projects = await fetchDefaultPrompts({
        headers,
      });
  
      return NextResponse.json(projects);
    } catch (error) {
      console.error("Unexpected error while fetching default prompts:", error);
      return NextResponse.json(
        { error: "Unexpected error while fetching default prompts." },
        { status: 500 }
      );
    }
}