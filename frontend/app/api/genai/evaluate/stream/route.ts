import { NextResponse } from "next/server";
import { evaluateStudiesStream } from "@/lib/api/genaiStreamApi";
import { getMeerkatHeaders } from "@/lib/server/meerkatHeaders";

export async function POST(request: Request) {
  try {
    const body = await request.text();
    const reqJson = JSON.parse(body);

    // Get meerkat headers (JWT for auth)
    const meerkatHeaders = await getMeerkatHeaders("application/json");
    const headersForStream = {
      ...meerkatHeaders,
      "Content-Type": "application/json",
    };

    // Create a ReadableStream to pipe SSE events from genaiStreamApi to the client
    let controller: ReadableStreamDefaultController<Uint8Array | string>;
    const stream = new ReadableStream<Uint8Array | string>({
      start(ctrl: ReadableStreamDefaultController<Uint8Array | string>) {
        controller = ctrl;

        evaluateStudiesStream(
          reqJson,
          {
            onEvent: (event) => {
              controller.enqueue(`data: ${JSON.stringify(event)}\n`);
            },
            onComplete: () => {
              controller.enqueue(`data: {\"event\":\"complete\"}\n`);
              controller.close();
            },
            onError: (err) => {
              controller.enqueue(`data: {\"event\":\"error\",\"message\":${JSON.stringify(err.message || "Unknown error")}}\n`);
              controller.close();
            },
          },
          { headers: headersForStream }
        );
      },
      cancel() {
        // No-op: abort handled by evaluateStudiesStream's return function if needed
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
      { detail: error instanceof Error ? error.message : "Failed to proxy stream" },
      { status: 502 }
    );
  }
}
