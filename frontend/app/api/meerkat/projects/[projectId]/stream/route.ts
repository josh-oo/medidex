import { NextRequest, NextResponse } from "next/server";
import { streamProjectUpdates } from "@/lib/api/projectApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function GET(
	_request: NextRequest,
	{ params }: { params: Promise<{ projectId: string }> }
) {
	const { projectId } = await params;

	if (!projectId) {
		return NextResponse.json(
			{ error: "Missing project id." },
			{ status: 400 }
		);
	}

	try {
		const meerkatHeaders = await getMeerkatHeaders("text/event-stream");

		let stopStream: (() => void) | undefined;
		const stream = new ReadableStream<Uint8Array | string>({
			start(controller: ReadableStreamDefaultController<Uint8Array | string>) {
				stopStream = streamProjectUpdates(
					projectId,
					{
						onEvent: (event) => {
							controller.enqueue(`data: ${JSON.stringify(event)}\n\n`);
						},
						onComplete: () => {
							controller.enqueue(`data: {"event":"complete"}\n\n`);
							controller.close();
						},
						onError: (err) => {
							controller.enqueue(
								`data: {"event":"error","message":${JSON.stringify(err.message || "Unknown error")}}\n\n`
							);
							controller.close();
						},
					},
					{ headers: meerkatHeaders }
				);
			},
			cancel() {
				stopStream?.();
			},
		});

		const headers = new Headers();
		headers.set("Content-Type", "text/event-stream");
		headers.set("Cache-Control", "no-cache");
		headers.set("Connection", "keep-alive");

		return new Response(stream, {
			status: 200,
			headers,
		});
	} catch (error) {
		return NextResponse.json(
			{
				detail:
					error instanceof Error
						? error.message
						: "Failed to proxy project stream",
			},
			{ status: 502 }
		);
	}
}
