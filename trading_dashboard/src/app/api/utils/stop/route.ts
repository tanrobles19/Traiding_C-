import { NextResponse } from "next/server";
import { killActiveChild } from "@/lib/pipeline-process";

// POST /api/utils/stop
//
// Sends SIGTERM to the active utils_pipeline.py child, if any. Returns:
//   200  { stopped: true }   — signal sent (child exits asynchronously;
//                              the run route's "exit" SSE event closes
//                              the stream and clears the singleton)
//   409  { stopped: false }  — no pipeline currently running

export const runtime = "nodejs";

export async function POST() {
  const ok = killActiveChild("SIGTERM");
  if (!ok) {
    return NextResponse.json(
      { stopped: false, error: "No pipeline is currently running." },
      { status: 409 }
    );
  }
  return NextResponse.json({ stopped: true });
}
