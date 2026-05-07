"use client";

import { useEffect, useState } from "react";
import {
  Play,
  Square,
  Loader2,
  CheckCircle2,
  XCircle,
  Circle,
  AlertTriangle,
  Database,
  Download,
  Gauge,
  SkipForward,
  Settings2,
  Filter,
  DollarSign,
  Layers,
} from "lucide-react";

type StepStatus = "pending" | "running" | "complete" | "skipped" | "error";

type StepState = {
  status: StepStatus;
  detail?: string;
  count?: number;
  total?: number;
  error?: string;
};

type PipelineState = {
  clear:      StepState;
  last_price: StepState;
  float:      StepState;
  historical: StepState;
  rv:         StepState;
};

type StepKey = keyof PipelineState;

const INITIAL: PipelineState = {
  clear:      { status: "pending" },
  last_price: { status: "pending" },
  float:      { status: "pending" },
  historical: { status: "pending" },
  rv:         { status: "pending" },
};

// ── Trading-config schema ────────────────────────────────────────
//
// Lives in /api/config (which reads/writes ../trading_config.json at
// the repo root). The C++ trader reads the same file at startup —
// changes here only take effect on the NEXT C++ run.

type TradingConfig = {
  relative_volume_factor: number;
  increase_from_open_pct: number;
  min_trade_size: number;
  low_activity_threshold: number;
  order_quantity: number;
  float_threshold: number;
  low_float_threshold: number;
  min_price: number;
  max_price: number;
  trade_capital: number;
  max_loss_tolerance_pct: number;
  historical_days: number;
  max_spread_abs: number;
};

// Field display order + labels + units. Drives both the read view and
// the edit form.
const CONFIG_FIELDS: {
  key: keyof TradingConfig;
  label: string;
  unit: string;
  step: number;
}[] = [
  { key: "relative_volume_factor", label: "Relative Volume Factor", unit: "× hourly baseline", step: 0.1 },
  { key: "increase_from_open_pct", label: "Increase Threshold",     unit: "% from open",       step: 0.1 },
  { key: "min_trade_size",         label: "Min Trade Size",         unit: "shares",            step: 1   },
  { key: "low_activity_threshold", label: "Activity Threshold",     unit: "fraction of secs",  step: 0.01},
  { key: "order_quantity",         label: "Order Quantity",         unit: "shares per BUY",    step: 1   },
  { key: "float_threshold",        label: "Float Threshold",        unit: "shares (max)",      step: 1000000 },
  { key: "low_float_threshold",    label: "Low Float Threshold",    unit: "shares — /low-float page cap", step: 1000000 },
  { key: "min_price",              label: "Min Price",              unit: "USD",               step: 0.01},
  { key: "max_price",              label: "Max Price",              unit: "USD",               step: 0.01},
  { key: "trade_capital",          label: "Trade Capital",          unit: "USD per trade",     step: 1   },
  { key: "max_loss_tolerance_pct", label: "Max Loss Tolerance",     unit: "% per trade",       step: 0.5 },
  { key: "historical_days",        label: "Historical Days",        unit: "business days (Step 4 download window)", step: 1 },
  { key: "max_spread_abs",         label: "Max Spread",             unit: "USD (BUY blocked if ask−bid exceeds this)", step: 0.01 },
];

type InfoResponse = {
  symbol_count: number;
  symbol_range: string;
  counts: {
    HistoryByMin:            number;
    RelativeVolumeRatioHour: number;
    minute_candlesticks:     number;
    trades:                  number;
  };
  generated_at: number;
};

const STEP_META: Record<StepKey, {
  label: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}> = {
  clear: {
    label: "Step 1 — Clear day-work tables",
    description: "Destructive: truncates Orders, TradeSignalsBuyPerSecond, RelativeVolumeRatioHour, HistoryByMin, HistoryByMinToday, minute_candlesticks, trades, QueueBehavior. Uncheck if you don't want to wipe today's session data.",
    icon: Database,
  },
  last_price: {
    label: "Step 2 — Last price → Stocks.close",
    description: "Updates the close price for EVERY ticker in Stocks via Polygon get_last_trade. No filter — must run before any price-based filtering.",
    icon: DollarSign,
  },
  float: {
    label: "Step 3 — Float → Stocks.float_value",
    description: "Fetches float / shares-outstanding from yfinance for the price-filtered subset only (avoids ~10 min wait for tickers we never trade).",
    icon: Layers,
  },
  historical: {
    label: "Step 4 — Load historical data → HistoryByMin",
    description: "Downloads minute-bar data from Polygon.io for the configured business-day window (see Trading Config → Historical Days). Filtered by price AND float.",
    icon: Download,
  },
  rv: {
    label: "Step 5 — Calculate relative volume → RelativeVolumeRatioHour",
    description: "Builds the per-symbol per-hour volume baseline used by the C++ RV filter.",
    icon: Gauge,
  },
};

function StatusIcon({ status }: { status: StepStatus }) {
  switch (status) {
    case "complete":  return <CheckCircle2 className="size-5 text-emerald-500" />;
    case "running":   return <Loader2     className="size-5 text-amber-500 animate-spin" />;
    case "error":     return <XCircle     className="size-5 text-red-500" />;
    case "skipped":   return <SkipForward className="size-5 text-zinc-400 dark:text-zinc-500" />;
    default:          return <Circle      className="size-5 text-zinc-300 dark:text-zinc-600" />;
  }
}

function StepCard({
  stepKey,
  state,
  delayMs,
  enabled,
  onToggle,
  toggleDisabled,
}: {
  stepKey: StepKey;
  state: StepState;
  delayMs: number;
  enabled: boolean;
  onToggle: (next: boolean) => void;
  toggleDisabled: boolean;
}) {
  const meta = STEP_META[stepKey];
  const Icon = meta.icon;
  const pct =
    state.total && state.total > 0
      ? Math.min(100, Math.round(((state.count ?? 0) / state.total) * 100))
      : null;

  return (
    <div
      className={`rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 shadow-lg shadow-black/5 dark:shadow-black/20 transition-opacity ${enabled ? "" : "opacity-60"}`}
      style={{
        animation: "fadeSlideUp 0.6s ease-out both",
        animationDelay: `${delayMs}ms`,
      }}
    >
      <div className="flex items-start gap-4">
        <div className="size-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
          <Icon className="size-5 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => onToggle(e.target.checked)}
              disabled={toggleDisabled}
              className="size-4 accent-amber-500 cursor-pointer disabled:cursor-not-allowed"
              aria-label={`Enable ${meta.label}`}
            />
            <StatusIcon status={state.status} />
            <span className="font-semibold text-zinc-900 dark:text-white">{meta.label}</span>
          </div>
          <div className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            {meta.description}
          </div>

          {state.detail && (
            <div className="mt-2 text-xs text-zinc-500 dark:text-zinc-400 font-mono">
              {state.detail}
            </div>
          )}

          {pct !== null && state.status === "running" && (
            <div className="mt-3 space-y-1">
              <div className="flex justify-between text-xs text-zinc-500 dark:text-zinc-400 tabular-nums">
                <span>{state.count?.toLocaleString()} / {state.total?.toLocaleString()}</span>
                <span>{pct}%</span>
              </div>
              <div className="h-1.5 rounded-full bg-zinc-200/50 dark:bg-white/[0.06] overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-amber-400 to-orange-500 transition-all duration-200"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )}

          {state.error && (
            <div className="mt-3 rounded-xl bg-red-500/10 border border-red-500/20 px-3 py-2 text-xs text-red-600 dark:text-red-400">
              <AlertTriangle className="size-3.5 inline mr-1" />
              {state.error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Configuration & Results panel ──────────────────────────────
// Static trading-config constants on the left, live MySQL counts on
// the right. Refreshed when the page mounts and again at the end of
// each pipeline run.

function ConfigurationPanel({
  info,
  loading,
}: {
  info: InfoResponse | null;
  loading: boolean;
}) {
  const fmt = (n: number) => n.toLocaleString("en-US");

  // Editable config — fetched from /api/config on mount, written back
  // on Save. The C++ trader reads the same JSON at startup, so the
  // notice below tells the operator the change isn't live until restart.
  const [config, setConfig] = useState<TradingConfig | null>(null);
  const [draft, setDraft] = useState<TradingConfig | null>(null);
  const [configErr, setConfigErr] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => (r.ok ? r.json() : Promise.reject(r.statusText)))
      .then((c: TradingConfig) => { setConfig(c); setDraft(c); })
      .catch((e) => setConfigErr(String(e)));
  }, []);

  const dirty = !!(config && draft) &&
    CONFIG_FIELDS.some((f) => config[f.key] !== draft[f.key]);

  async function save() {
    if (!draft) return;
    setSaving(true);
    setConfigErr(null);
    try {
      const body: Partial<TradingConfig> = {};
      for (const f of CONFIG_FIELDS) body[f.key] = draft[f.key];
      const r = await fetch("/api/config", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        throw new Error(j.error || `HTTP ${r.status}`);
      }
      const j = await r.json();
      setConfig(j.config);
      setDraft(j.config);
      setSavedAt(Date.now());
    } catch (e) {
      setConfigErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function reset() {
    if (config) setDraft({ ...config });
  }

  const dbRows: { label: string; value: string; hint: string }[] = info
    ? [
        { label: "HistoryByMin",            value: fmt(info.counts.HistoryByMin),            hint: "Step 2" },
        { label: "RelativeVolumeRatioHour", value: fmt(info.counts.RelativeVolumeRatioHour), hint: "Step 3" },
        { label: "minute_candlesticks",     value: fmt(info.counts.minute_candlesticks),     hint: "intraday" },
        { label: "trades",                  value: fmt(info.counts.trades),                  hint: "intraday" },
      ]
    : [];

  return (
    <div
      className="rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 shadow-lg shadow-black/5 dark:shadow-black/20"
      style={{
        animation: "fadeSlideUp 0.6s ease-out both",
        animationDelay: "440ms",
      }}
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="size-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center shrink-0">
          <Settings2 className="size-5 text-amber-600 dark:text-amber-400" />
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
            Configuration & Results
          </div>
          <div className="text-base font-semibold text-zinc-900 dark:text-white">
            Trading config + database snapshot
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-zinc-500 mb-2 flex items-center justify-between">
            <span>trading_config.json (editable)</span>
            {savedAt && !dirty && (
              <span className="text-emerald-600 dark:text-emerald-400 normal-case tracking-normal text-[11px]">
                saved · restart C++ trader to apply
              </span>
            )}
          </div>

          <div className="mb-2 text-xs flex items-center gap-2">
            <span className="text-zinc-500 dark:text-zinc-400">
              Symbols Processed:
            </span>
            <span className="font-mono text-zinc-900 dark:text-zinc-100">
              {loading ? "…" : info ? fmt(info.symbol_count) : "—"}
            </span>
          </div>

          {configErr && (
            <div className="mb-2 text-xs text-red-500 flex items-center gap-1.5">
              <AlertTriangle className="size-3.5" />
              {configErr}
            </div>
          )}

          {!draft && !configErr && (
            <div className="text-sm text-zinc-500 dark:text-zinc-400">
              <Loader2 className="size-3.5 inline animate-spin mr-2" />
              Loading…
            </div>
          )}

          {draft && (
            <>
              <div className="space-y-1.5">
                {CONFIG_FIELDS.map((f) => (
                  <div key={f.key} className="flex items-center gap-2 text-sm">
                    <label
                      htmlFor={`cfg-${f.key}`}
                      className="text-zinc-500 dark:text-zinc-400 shrink-0 w-44"
                    >
                      {f.label}
                    </label>
                    <input
                      id={`cfg-${f.key}`}
                      type="number"
                      step={f.step}
                      value={draft[f.key]}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          [f.key]: Number(e.target.value),
                        })
                      }
                      className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100 bg-white/40 dark:bg-zinc-950/40 border border-zinc-900/10 dark:border-white/10 rounded-md px-2 py-1 w-28 focus:outline-none focus:ring-1 focus:ring-amber-500/40"
                    />
                    <span className="text-[11px] text-zinc-400 dark:text-zinc-500">
                      {f.unit}
                    </span>
                  </div>
                ))}
              </div>

              <div className="flex items-center gap-2 mt-3 pt-3 border-t border-zinc-900/5 dark:border-white/5">
                <button
                  onClick={save}
                  disabled={!dirty || saving}
                  className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-black text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.97] transition-transform"
                >
                  {saving ? (
                    <>
                      <Loader2 className="size-3.5 inline animate-spin mr-1.5" />
                      Saving…
                    </>
                  ) : (
                    "Save"
                  )}
                </button>
                <button
                  onClick={reset}
                  disabled={!dirty || saving}
                  className="px-3 py-1.5 rounded-xl bg-zinc-900/[0.05] dark:bg-white/[0.05] border border-zinc-900/10 dark:border-white/10 text-sm text-zinc-700 dark:text-zinc-300 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Reset
                </button>
                {dirty && (
                  <span className="text-[11px] text-amber-600 dark:text-amber-400 ml-2">
                    unsaved changes
                  </span>
                )}
              </div>
            </>
          )}
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-zinc-500 mb-2">
            Database status (live row counts)
          </div>
          {loading && !info ? (
            <div className="text-sm text-zinc-500 dark:text-zinc-400">
              <Loader2 className="size-3.5 inline animate-spin mr-2" />
              Loading…
            </div>
          ) : info ? (
            <dl className="space-y-1.5 text-sm">
              {dbRows.map((r) => (
                <div key={r.label} className="flex items-baseline gap-3">
                  <dt className="text-zinc-500 dark:text-zinc-400 shrink-0 w-48">
                    {r.label}
                  </dt>
                  <dd className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100">
                    {r.value}
                    <span className="ml-2 text-[10px] uppercase tracking-wider text-zinc-400 dark:text-zinc-600">
                      {r.hint}
                    </span>
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <div className="text-sm text-red-500">
              Failed to load live counts
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// Symbol-selection thresholds carried by the {type:"config"} event the
// pipeline emits at startup. Surfaced in the run banner so the operator
// can verify the run is using the values they just saved.
type RunConfig = {
  min_price: number;
  max_price: number;
  float_threshold: number;
};

// Default enabled flag per step. All ON — operator unchecks any step
// that's already up to date for the day (e.g. last_price already ran).
const DEFAULT_ENABLED: Record<StepKey, boolean> = {
  clear:      true,
  last_price: true,
  float:      true,
  historical: true,
  rv:         true,
};

export default function UtilsPage() {
  const [running, setRunning] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [enabled, setEnabled] = useState<Record<StepKey, boolean>>(DEFAULT_ENABLED);
  const [pipeline, setPipeline] = useState<PipelineState>(INITIAL);
  const [exitCode, setExitCode] = useState<number | null>(null);
  const [info, setInfo] = useState<InfoResponse | null>(null);
  const [infoLoading, setInfoLoading] = useState(true);
  const [runConfig, setRunConfig] = useState<RunConfig | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  async function refreshInfo() {
    setInfoLoading(true);
    try {
      const r = await fetch("/api/utils/info");
      if (r.ok) setInfo(await r.json());
    } catch {
      /* ignore */
    } finally {
      setInfoLoading(false);
    }
  }

  useEffect(() => {
    refreshInfo();
  }, []);

  function handleEvent(evt: Record<string, unknown>) {
    const type = evt.type as string;

    if (type === "config") {
      const min = Number(evt.min_price);
      const max = Number(evt.max_price);
      const flt = Number(evt.float_threshold);
      if (Number.isFinite(min) && Number.isFinite(max) && Number.isFinite(flt)) {
        setRunConfig({ min_price: min, max_price: max, float_threshold: flt });
      }
    } else if (type === "step") {
      const step = evt.step as StepKey;
      const status = evt.status as StepStatus;
      setPipeline((prev) => {
        const next = { ...prev };
        const detailParts: string[] = [];
        if (typeof evt.init === "string" && typeof evt.end === "string") {
          detailParts.push(`${evt.init} → ${evt.end}`);
        }
        next[step] = {
          ...next[step],
          status,
          detail: detailParts.join(" · ") || prev[step].detail,
          error: undefined,
        };
        return next;
      });
    } else if (type === "progress") {
      const step = evt.step as StepKey;
      const count = Number(evt.count);
      const total = Number(evt.total);
      setPipeline((prev) => ({
        ...prev,
        [step]: {
          ...prev[step],
          count,
          total,
          detail:
            typeof evt.symbol === "string"
              ? `current: ${evt.symbol}`
              : prev[step].detail,
        },
      }));
    } else if (type === "error") {
      const step = evt.step as StepKey | undefined;
      const message = String(evt.message ?? "Unknown error");
      if (step && step in pipeline) {
        setPipeline((prev) => ({
          ...prev,
          [step]: { ...prev[step], status: "error", error: message },
        }));
      }
    } else if (type === "exit") {
      setExitCode(typeof evt.code === "number" ? evt.code : null);
    }
  }

  async function run() {
    setRunning(true);
    setExitCode(null);
    setRunError(null);
    setRunConfig(null);

    // Pre-populate "skipped" for any unchecked step so the UI reflects
    // the planned run from the moment it starts (Python will also emit
    // a confirming "skipped" event when it gets there).
    const initialState: PipelineState = { ...INITIAL };
    (Object.keys(initialState) as StepKey[]).forEach((k) => {
      if (!enabled[k]) initialState[k] = { status: "skipped" };
    });
    setPipeline(initialState);

    const res = await fetch("/api/utils/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps: enabled }),
    });

    if (!res.ok || !res.body) {
      const body = await res.json().catch(() => ({}));
      setRunError(body.error ?? `Run failed (${res.status})`);
      setRunning(false);
      return;
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
        try {
          handleEvent(JSON.parse(json));
        } catch {
          /* ignore malformed line */
        }
      }
    }

    setRunning(false);
    setStopping(false);
    // Pipeline finished — refresh the live counts panel.
    refreshInfo();
  }

  async function stop() {
    setStopping(true);
    try {
      const r = await fetch("/api/utils/stop", { method: "POST" });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        setRunError(body.error ?? `Stop failed (${r.status})`);
      }
    } catch (e) {
      setRunError((e as Error).message);
    }
    // The /api/utils/run SSE stream will see the child exit and close;
    // the reader loop then sets running=false and stopping=false.
  }

  return (
    <div className="px-8 py-8 max-w-5xl mx-auto">
      <div style={{ animation: "fadeSlideUp 0.6s ease-out both" }}>
        <div className="text-[11px] uppercase tracking-[0.22em] text-zinc-500">
          Data Pipeline
        </div>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-zinc-900 dark:text-white">
          Load data for trading
        </h1>
        <div className="mt-3 h-0.5 w-16 rounded-full bg-gradient-to-r from-amber-400 to-orange-500" />
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400 max-w-2xl">
          Runs the three-step pre-market pipeline: optionally wipes
          day-work tables, downloads the configured business-day
          window of minute-bar data from Polygon.io (see Historical
          Days in Trading Config below), then re-computes the hourly
          relative-volume baseline used by the C++ RV filter.
        </p>
      </div>

      {/* ── Run button + opt-in clear ──────────────────────────── */}
      <div
        className="mt-8 rounded-2xl bg-zinc-900/[0.03] dark:bg-white/[0.03] border border-zinc-900/5 dark:border-white/5 p-5 shadow-lg shadow-black/5 dark:shadow-black/20"
        style={{ animation: "fadeSlideUp 0.6s ease-out both", animationDelay: "120ms" }}
      >
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="text-sm text-zinc-500 dark:text-zinc-400">
            Each step has its own checkbox below. Uncheck any step that
            already ran today to skip it on this run.
          </div>

          <div className="flex items-center gap-2">
            {running && (
              <button
                onClick={stop}
                disabled={stopping}
                className="inline-flex items-center gap-2 px-5 h-11 rounded-xl bg-red-500/10 border border-red-500/30 text-sm font-semibold text-red-600 dark:text-red-400 transition-all duration-300 hover:bg-red-500/20 hover:border-red-500/50 active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed"
                title="Send SIGTERM to the running pipeline"
              >
                {stopping ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Square className="size-4" />
                )}
                {stopping ? "Stopping…" : "Stop"}
              </button>
            )}

            <button
              onClick={run}
              disabled={running}
              className="inline-flex items-center gap-2 px-6 h-11 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-sm font-semibold text-black transition-all duration-300 hover:from-amber-400 hover:to-orange-400 hover:shadow-lg hover:shadow-amber-500/20 active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {running ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Play className="size-4" />
              )}
              {running ? "Running…" : "Load data for trading"}
            </button>
          </div>
        </div>

        {runConfig && (
          <div className="mt-4 rounded-xl bg-amber-500/5 border border-amber-500/20 px-4 py-3 text-sm flex items-center gap-3 flex-wrap">
            <Filter className="size-4 text-amber-600 dark:text-amber-400 shrink-0" />
            <span className="text-zinc-500 dark:text-zinc-400 text-xs uppercase tracking-wider">
              Active filters from trading_config.json
            </span>
            <span className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100">
              ${runConfig.min_price.toFixed(2)} ≤ price ≤ ${runConfig.max_price.toFixed(2)}
            </span>
            <span className="text-zinc-400 dark:text-zinc-600">·</span>
            <span className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100">
              float &lt; {runConfig.float_threshold.toLocaleString()}
            </span>
          </div>
        )}

        {runError && (
          <div className="mt-4 rounded-xl bg-red-500/10 border border-red-500/30 px-4 py-3 text-sm text-red-600 dark:text-red-400 flex items-center gap-2">
            <AlertTriangle className="size-4 shrink-0" />
            {runError}
          </div>
        )}
      </div>

      {/* ── Step cards ────────────────────────────────────────── */}
      <div className="mt-6 space-y-4">
        {(["clear", "last_price", "float", "historical", "rv"] as StepKey[]).map((k, i) => (
          <StepCard
            key={k}
            stepKey={k}
            state={pipeline[k]}
            delayMs={200 + i * 60}
            enabled={enabled[k]}
            onToggle={(next) => setEnabled((prev) => ({ ...prev, [k]: next }))}
            toggleDisabled={running}
          />
        ))}
      </div>

      {/* ── Configuration & Results ──────────────────────────── */}
      <div className="mt-6">
        <ConfigurationPanel info={info} loading={infoLoading} />
      </div>

      {/* ── Final status ─────────────────────────────────────── */}
      {exitCode !== null && (
        <div
          className={`mt-6 rounded-2xl border px-5 py-4 text-sm shadow-lg shadow-black/5 dark:shadow-black/20 ${
            exitCode === 0
              ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-700 dark:text-emerald-300"
              : "bg-red-500/10 border-red-500/20 text-red-700 dark:text-red-300"
          }`}
        >
          {exitCode === 0
            ? "Pipeline finished successfully. System ready for trading."
            : `Pipeline exited with code ${exitCode}. Check the step error message above.`}
        </div>
      )}
    </div>
  );
}
