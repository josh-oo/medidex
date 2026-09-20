import { NextResponse } from "next/server";
import { getAnnotations } from "@/lib/api/projectApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function GET(
	_request: Request,
	{ params }: { params: Promise<{ projectId: string }> }
) {
	const resolvedParams = await params;
	const { projectId } = resolvedParams;

	if (!projectId) {
		return NextResponse.json({ detail: "projectId is required" }, { status: 400 });
	}

	try {
		const headers = await getMeerkatHeaders();
		const annotations = await getAnnotations(projectId, { headers });
		return NextResponse.json(annotations, { status: 200 });
	} catch (error) {
		console.error(`Failed to fetch annotations for project ${projectId}:`, error);
		const detail =
			error instanceof Error && error.message
				? error.message
				: "Failed to fetch project annotations";
		const status = (error as { status?: number })?.status;
		return NextResponse.json(
			{ detail },
			{ status: typeof status === "number" ? status : 500 }
		);
	}
}
