"use client";

import { useState } from "react";
import {
  Download,
  Loader2,
  CheckCircle2,
  XCircle,
  Circle,
  AlertTriangle,
  CloudDownload,
  DatabaseZap,
} from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const fieldClasses =
  "h-10 rounded-xl border border-zinc-900/10 dark:border-white/10 bg-white/60 dark:bg-white/[0.03] text-sm text-zinc-900 dark:text-zinc-100 outline-none transition-all duration-200 focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20 placeholder:text-zinc-400 dark:placeholder:text-zinc-600 px-3 font-mono tabular-nums";

type StepStatus = "pending" | "running" | "complete" | "skipped" | "error";
type StepKey =
  | "download_trades"
  | "save_trades"
  | "download_quotes"
  | "save_quotes";
type StepState = { status: StepStatus; count?: number; total?: number; error?: string };

const INITIAL: Record<StepKey, StepState> = {
  download_trades: { status: "pending" },
  save_trades:     { status: "pending" },
  download_quotes: { status: "pending" },
  save_quotes:     { status: "pending" },
};

const STEP_META: Record<StepKey, { label: string; icon: React.ComponentType<{ className?: string }> }> = {
  download_trades: { label: "Download trades from Polygon.io",  icon: CloudDownload },
  save_trades:     { label: "Save into MySQL · RawTrades",      icon: DatabaseZap },
  download_quotes: { label: "Download quotes from Polygon.io",  icon: CloudDownload },
  save_quotes:     { label: "Save into MySQL · RawQuotes",      icon: DatabaseZap },
};

function StatusIcon({ status }: { status: StepStatus }) {
  switch (status) {
    case "complete": return <CheckCircle2 className="size-4 text-emerald-500" />;
    case "running":  return <Loader2     className="size-4 text-amber-500 animate-spin" />;
    case "error":    return <XCircle     className="size-4 text-red-500" />;
    default:         return <Circle      className="size-4 text-zinc-300 dark:text-zinc-600" />;
  }
}

function StepRow({ stepKey, state }: { stepKey: StepKey; state: StepState }) {
  const meta = STEP_META[stepKey];
  const Icon = meta.icon;
  const pct =
    state.total && state.total > 0
      ? Math.min(100, Math.round(((state.count ?? 0) / state.total) * 100))
      : null;

  return (
    <div className="rounded-xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-3">
      <div className="flex items-center gap-3">
        <div className="size-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
          <Icon className="size-4 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <StatusIcon status={state.status} />
            <span className="text-sm font-medium text-zinc-900 dark:text-white">
              {meta.label}
            </span>
            {state.count !== undefined && (
              <span className="ml-auto text-xs font-mono tabular-nums text-zinc-500 dark:text-zinc-400">
                {state.count.toLocaleString()}
                {state.total ? ` / ${state.total.toLocaleString()}` : ""}
              </span>
            )}
          </div>
          {pct !== null && state.status === "running" && (
            <div className="mt-2 h-1 rounded-full bg-zinc-200/50 dark:bg-white/[0.06] overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-amber-400 to-orange-500 transition-all duration-200"
                style={{ width: `${pct}%` }}
              />
            </div>
          )}
          {state.error && (
            <div className="mt-2 text-xs text-red-600 dark:text-red-400">
              <AlertTriangle className="size-3 inline mr-1" />
              {state.error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

type FormState = {
  year: string; month: string; day: string;
  hour: string; minute: string; symbol: string;
};

const DEFAULT_FORM: FormState = {
  year:   "2026",
  month:  "1",
  day:    "26",
  hour:   "15",
  minute: "10",
  symbol: "PHGE",
};

export function DownloadTradesDialog({ apiPath }: { apiPath: string }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<FormState>(DEFAULT_FORM);
  const [running, setRunning] = useState(false);
  const [steps, setSteps] = useState(INITIAL);
  const [savedCount, setSavedCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  function update<K extends keyof FormState>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  function reset() {
    setSteps(INITIAL);
    setSavedCount(null);
    setError(null);
  }

  function handleEvent(evt: Record<string, unknown>) {
    const type = evt.type as string;

    if (type === "step") {
      const step = evt.step as StepKey;
      const status = evt.status as StepStatus;
      const count = typeof evt.count === "number" ? evt.count : undefined;
      setSteps((prev) => ({ ...prev, [step]: { ...prev[step], status, count, error: undefined } }));
    } else if (type === "progress") {
      const step = evt.step as StepKey;
      const count = Number(evt.count);
      const total = typeof evt.total === "number" ? evt.total : undefined;
      setSteps((prev) => ({ ...prev, [step]: { ...prev[step], count, total } }));
    } else if (type === "error") {
      const step = (evt.step as StepKey) ?? "download_trades";
      const message = String(evt.message ?? "Unknown error");
      setSteps((prev) => ({ ...prev, [step]: { ...prev[step], status: "error", error: message } }));
      setError(message);
    } else if (type === "done") {
      // 2026-05-05: pipeline now emits trades_saved + quotes_saved.
      // Sum them for the legacy `savedCount` UI element. Old single
      // `saved` field is supported as a fallback for the trades-only
      // legacy script.
      const tradesSaved = typeof evt.trades_saved === "number" ? evt.trades_saved : 0;
      const quotesSaved = typeof evt.quotes_saved === "number" ? evt.quotes_saved : 0;
      const legacy      = typeof evt.saved        === "number" ? evt.saved        : 0;
      const total = tradesSaved + quotesSaved + legacy;
      setSavedCount(total > 0 ? total : null);
    }
  }

  async function run(e: React.FormEvent) {
    e.preventDefault();
    reset();

    const payload = {
      year:   Number(form.year),
      month:  Number(form.month),
      day:    Number(form.day),
      hour:   Number(form.hour),
      minute: Number(form.minute),
      symbol: form.symbol.trim().toUpperCase(),
    };

    if (!payload.symbol) { setError("Symbol is required"); return; }
    if (!Number.isInteger(payload.year)  || !Number.isInteger(payload.month)  ||
        !Number.isInteger(payload.day)   || !Number.isInteger(payload.hour)   ||
        !Number.isInteger(payload.minute)) {
      setError("Year / month / day / hour / minute must be integers");
      return;
    }

    setRunning(true);
    try {
      const res = await fetch(apiPath, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify(payload),
      });
      if (!res.ok || !res.body) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `request failed (${res.status})`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const json = line.slice(6).trim();
          if (!json) continue;
          try { handleEvent(JSON.parse(json)); } catch { /* ignore */ }
        }
      }

      // refresh the table + sidebar counts
      await queryClient.invalidateQueries({ queryKey: ["/api/raw-trades"] });
      await queryClient.invalidateQueries({ queryKey: ["raw-trades-info"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setRunning(false);
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 px-4 h-9 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-sm font-semibold text-black transition-all duration-300 hover:from-amber-400 hover:to-orange-400 hover:shadow-lg hover:shadow-amber-500/20 active:scale-[0.97]"
      >
        <Download className="size-4" />
        Download trades & quotes
      </button>

      <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { reset(); setRunning(false); } }}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Download tick-level trades & quotes</DialogTitle>
            <DialogDescription>
              Pulls every trade AND every NBBO quote for one symbol over a
              single minute from Polygon.io and saves them into the MySQL
              {" "}<span className="font-mono">RawTrades</span> and
              {" "}<span className="font-mono">RawQuotes</span> tables.
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={run} className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="year" className="text-[10px] font-medium uppercase tracking-widest text-zinc-500">Year</Label>
                <Input id="year" type="number" inputMode="numeric" value={form.year} onChange={(e) => update("year", e.target.value)} className={fieldClasses} required />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="month" className="text-[10px] font-medium uppercase tracking-widest text-zinc-500">Month</Label>
                <Input id="month" type="number" inputMode="numeric" min={1} max={12} value={form.month} onChange={(e) => update("month", e.target.value)} className={fieldClasses} required />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="day" className="text-[10px] font-medium uppercase tracking-widest text-zinc-500">Day</Label>
                <Input id="day" type="number" inputMode="numeric" min={1} max={31} value={form.day} onChange={(e) => update("day", e.target.value)} className={fieldClasses} required />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="hour" className="text-[10px] font-medium uppercase tracking-widest text-zinc-500">Hour (0–23)</Label>
                <Input id="hour" type="number" inputMode="numeric" min={0} max={23} value={form.hour} onChange={(e) => update("hour", e.target.value)} className={fieldClasses} required />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="minute" className="text-[10px] font-medium uppercase tracking-widest text-zinc-500">Minute</Label>
                <Input id="minute" type="number" inputMode="numeric" min={0} max={59} value={form.minute} onChange={(e) => update("minute", e.target.value)} className={fieldClasses} required />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="symbol" className="text-[10px] font-medium uppercase tracking-widest text-zinc-500">Symbol</Label>
                <Input id="symbol" value={form.symbol} onChange={(e) => update("symbol", e.target.value.toUpperCase())} className={fieldClasses} placeholder="PHGE" required />
              </div>
            </div>

            <div className="space-y-2">
              <StepRow stepKey="download_trades" state={steps.download_trades} />
              <StepRow stepKey="save_trades"     state={steps.save_trades} />
              <StepRow stepKey="download_quotes" state={steps.download_quotes} />
              <StepRow stepKey="save_quotes"     state={steps.save_quotes} />
            </div>

            {savedCount !== null && (
              <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
                Saved <span className="font-mono tabular-nums">{savedCount.toLocaleString()}</span> row{savedCount === 1 ? "" : "s"} across RawTrades + RawQuotes.
              </div>
            )}

            {error && savedCount === null && (
              <div className="rounded-xl bg-red-500/10 border border-red-500/20 px-3 py-2 text-sm text-red-600 dark:text-red-400">
                {error}
              </div>
            )}

            <DialogFooter>
              <button
                type="button"
                onClick={() => { setOpen(false); setForm(DEFAULT_FORM); reset(); }}
                className="px-4 h-9 rounded-xl text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white transition-colors"
                disabled={running}
              >
                Close
              </button>
              <button
                type="submit"
                disabled={running}
                className="inline-flex items-center gap-2 px-5 h-9 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-sm font-semibold text-black transition-all duration-300 hover:from-amber-400 hover:to-orange-400 hover:shadow-lg hover:shadow-amber-500/20 active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {running ? <Loader2 className="size-4 animate-spin" /> : <Download className="size-4" />}
                {running ? "Running…" : "Run download"}
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
