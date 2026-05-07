import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import path from "path";
import { hasActiveChild, setActiveChild } from "@/lib/pipeline-process";

// POST /api/utils/run
//
// Spawns ../utils_pipeline.py and streams its stdout (one JSON event
// per line) back to the client as Server-Sent Events. The frontend
// reads the stream with fetch + ReadableStream.getReader().
//
// Body (optional):
//   { clear: boolean }   // when true, includes the destructive
//                        // clear-day-work-tables step (default: false)
//
// Each SSE message is `data: <json>\n\n`. The Python script's emitted
// events are forwarded verbatim plus an `{"type":"exit","code":N}`
// at the end.
//
// Concurrency: at most one pipeline runs at a time. A second POST
// while one is in flight returns 409. The child reference lives in
// `lib/pipeline-process` so /api/utils/stop can SIGTERM it.

export const runtime = "nodejs";   // child_process not available in edge

function sseLine(json: string): string {
  return `data: ${json}\n\n`;
}

export async function POST(req: NextRequest) {
  // Refuse to spawn a second pipeline if one is already running. The
  // existing child reference is owned by the previous request's
  // ReadableStream.
  if (hasActiveChild()) {
    return NextResponse.json(
      { error: "A pipeline run is already in progress. Stop it before starting a new one." },
      { status: 409 }
    );
  }

  // Per-step toggles. The dashboard sends a `steps` map of booleans —
  // one entry per step. `true` means "run this step", `false` means
  // "skip it". Anything missing defaults to true (run by default).
  type StepKey = "clear" | "last_price" | "float" | "historical" | "rv";
  const stepFlags: Record<StepKey, string> = {
    clear:      "--skip-clear",
    last_price: "--skip-last-price",
    float:      "--skip-float",
    historical: "--skip-historical",
    rv:         "--skip-rv",
  };
  let steps: Partial<Record<StepKey, boolean>> = {};
  try {
    const body = await req.json();
    if (body?.steps && typeof body.steps === "object") {
      steps = body.steps as Partial<Record<StepKey, boolean>>;
    }
  } catch {
    /* no body — all steps default to enabled */
  }

  // Pipeline lives at the repo root (one level up from the dashboard).
  const cwd = path.resolve(process.cwd(), "..");
  const args = ["utils_pipeline.py"];
  for (const k of Object.keys(stepFlags) as StepKey[]) {
    if (steps[k] === false) args.push(stepFlags[k]);
  }

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder();
      const send = (json: string) => controller.enqueue(enc.encode(sseLine(json)));

      // Ensure we use the project's virtualenv if available; fall back
      // to system python3 otherwise.
      const child = spawn("python3", args, {
        cwd,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: "1",
          // Prepend the venv to PATH so `python3` resolves to it.
          PATH: `${cwd}/myenv/bin:${process.env.PATH ?? ""}`,
        },
      });

      // Register so /api/utils/stop can find and kill it.
      setActiveChild(child);

      let buffer = "";

      child.stdout.on("data", (chunk: Buffer) => {
        buffer += chunk.toString();
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed) send(trimmed);
        }
      });

      child.stderr.on("data", (chunk: Buffer) => {
        // Forward stderr as a synthetic event so the UI can show it.
        send(JSON.stringify({ type: "stderr", message: chunk.toString() }));
      });

      child.on("error", (err) => {
        send(JSON.stringify({ type: "spawn_error", message: err.message }));
      });

      child.on("exit", (code, signal) => {
        if (buffer.trim()) {
          send(buffer.trim());
          buffer = "";
        }
        send(JSON.stringify({ type: "exit", code, signal }));
        // Clear singleton so future runs are allowed.
        setActiveChild(null);
        controller.close();
      });
    },
    cancel() {
      // Client disconnected — leave the child running so partial work
      // (e.g. a half-loaded HistoryByMin) at least finishes its current
      // step. Operator can stop explicitly via /api/utils/stop.
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
