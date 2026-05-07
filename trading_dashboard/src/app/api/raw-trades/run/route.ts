import { NextRequest } from "next/server";
import { spawn } from "child_process";
import path from "path";

// POST /api/raw-trades/run
//
// Body: { year, month, day, hour, minute, symbol }
//
// Spawns ../download_trades_pipeline.py and streams its stdout (one
// JSON event per line) back to the client as Server-Sent Events.

export const runtime = "nodejs";

function sseLine(json: string): string {
  return `data: ${json}\n\n`;
}

function isInt(n: unknown): n is number {
  return typeof n === "number" && Number.isInteger(n);
}

export async function POST(req: NextRequest) {
  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const { year, month, day, hour, minute, symbol } = body as {
    year?: number; month?: number; day?: number;
    hour?: number; minute?: number; symbol?: string;
  };

  if (
    !isInt(year)  || !isInt(month) || !isInt(day) ||
    !isInt(hour)  || !isInt(minute) ||
    typeof symbol !== "string" || !symbol.trim()
  ) {
    return Response.json(
      { error: "Required: integer year/month/day/hour/minute + non-empty symbol" },
      { status: 400 },
    );
  }

  // Reject anything that isn't a clean ticker — the value is passed as a
  // CLI argument so we want it tightly bounded even though spawn() avoids
  // shell interpretation.
  const cleanSymbol = symbol.trim().toUpperCase();
  if (!/^[A-Z][A-Z0-9.\-_]{0,9}$/.test(cleanSymbol)) {
    return Response.json({ error: `Invalid symbol: ${symbol}` }, { status: 400 });
  }
  if (month < 1 || month > 12 || day < 1 || day > 31 ||
      hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    return Response.json({ error: "Out-of-range date/time field" }, { status: 400 });
  }

  const cwd = path.resolve(process.cwd(), "..");
  const args = [
    "download_trades_pipeline.py",
    "--year",   String(year),
    "--month",  String(month),
    "--day",    String(day),
    "--hour",   String(hour),
    "--minute", String(minute),
    "--symbol", cleanSymbol,
  ];

  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const enc = new TextEncoder();
      const send = (json: string) =>
        controller.enqueue(enc.encode(sseLine(json)));

      const child = spawn("python3", args, {
        cwd,
        env: {
          ...process.env,
          PYTHONUNBUFFERED: "1",
          PATH: `${cwd}/myenv/bin:${process.env.PATH ?? ""}`,
        },
      });

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
        controller.close();
      });
    },
    cancel() { /* leave child to finish */ },
  });

  return new Response(stream, {
    headers: {
      "Content-Type":  "text/event-stream",
      "Cache-Control": "no-cache",
      Connection:      "keep-alive",
    },
  });
}
