"use client";

import { useState } from "react";
import { Plus, Loader2 } from "lucide-react";
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
  "h-10 rounded-xl border border-zinc-900/10 dark:border-white/10 bg-white/60 dark:bg-white/[0.03] text-sm text-zinc-900 dark:text-zinc-100 outline-none transition-all duration-200 focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20 placeholder:text-zinc-400 dark:placeholder:text-zinc-600";

type FormState = {
  ticker: string;
  close: string;
  float_value: string;
  short_percent_float: string;
  avg_month_volume: string;
  shares_outstanding: string;
  shares_short: string;
};

const EMPTY: FormState = {
  ticker: "",
  close: "",
  float_value: "",
  short_percent_float: "",
  avg_month_volume: "",
  shares_outstanding: "",
  shares_short: "",
};

function toNumberOrNull(s: string): number | null {
  if (!s.trim()) return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}

export function AddStockDialog({ apiPath }: { apiPath: string }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  function update<K extends keyof FormState>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const ticker = form.ticker.trim().toUpperCase();
    if (!ticker) {
      setError("Ticker is required");
      return;
    }

    setSubmitting(true);
    try {
      const r = await fetch(apiPath, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ticker,
          close:               toNumberOrNull(form.close),
          float_value:         toNumberOrNull(form.float_value),
          short_percent_float: toNumberOrNull(form.short_percent_float),
          avg_month_volume:    toNumberOrNull(form.avg_month_volume),
          shares_outstanding:  toNumberOrNull(form.shares_outstanding),
          shares_short:        toNumberOrNull(form.shares_short),
        }),
      });

      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.error ?? `Request failed (${r.status})`);
      }

      // success — reset, close, refresh
      setForm(EMPTY);
      setOpen(false);
      await queryClient.invalidateQueries({ queryKey: [apiPath] });
      await queryClient.invalidateQueries({ queryKey: ["stats"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-2 px-4 h-9 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-sm font-semibold text-black transition-all duration-300 hover:from-amber-400 hover:to-orange-400 hover:shadow-lg hover:shadow-amber-500/20 active:scale-[0.97]"
      >
        <Plus className="size-4" />
        Add stock
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
        <DialogHeader>
          <DialogTitle>Add stock</DialogTitle>
          <DialogDescription>
            Insert a new row into the Stocks registry. Only the ticker is required.
            Other fields are filled in by the Python pre-market pipeline.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2 space-y-1.5">
              <Label htmlFor="ticker" className="text-xs font-medium uppercase tracking-widest text-zinc-500">
                Ticker *
              </Label>
              <Input
                id="ticker"
                value={form.ticker}
                onChange={(e) => update("ticker", e.target.value)}
                className={fieldClasses}
                placeholder="NVDA"
                autoFocus
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="close" className="text-xs font-medium uppercase tracking-widest text-zinc-500">Last close</Label>
              <Input id="close" type="number" step="any" inputMode="decimal" value={form.close} onChange={(e) => update("close", e.target.value)} className={fieldClasses} placeholder="0.00" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="float_value" className="text-xs font-medium uppercase tracking-widest text-zinc-500">Float</Label>
              <Input id="float_value" type="number" inputMode="numeric" value={form.float_value} onChange={(e) => update("float_value", e.target.value)} className={fieldClasses} placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="short_percent_float" className="text-xs font-medium uppercase tracking-widest text-zinc-500">Short %</Label>
              <Input id="short_percent_float" type="number" inputMode="numeric" value={form.short_percent_float} onChange={(e) => update("short_percent_float", e.target.value)} className={fieldClasses} placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="avg_month_volume" className="text-xs font-medium uppercase tracking-widest text-zinc-500">Avg month volume</Label>
              <Input id="avg_month_volume" type="number" inputMode="numeric" value={form.avg_month_volume} onChange={(e) => update("avg_month_volume", e.target.value)} className={fieldClasses} placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="shares_outstanding" className="text-xs font-medium uppercase tracking-widest text-zinc-500">Shares outstanding</Label>
              <Input id="shares_outstanding" type="number" inputMode="numeric" value={form.shares_outstanding} onChange={(e) => update("shares_outstanding", e.target.value)} className={fieldClasses} placeholder="0" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="shares_short" className="text-xs font-medium uppercase tracking-widest text-zinc-500">Shares short</Label>
              <Input id="shares_short" type="number" inputMode="numeric" value={form.shares_short} onChange={(e) => update("shares_short", e.target.value)} className={fieldClasses} placeholder="0" />
            </div>
          </div>

          {error && (
            <div className="rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-600 dark:text-red-400">
              {error}
            </div>
          )}

          <DialogFooter>
            <button
              type="button"
              onClick={() => { setOpen(false); setForm(EMPTY); setError(null); }}
              className="px-4 h-9 rounded-xl text-sm text-zinc-500 hover:text-zinc-900 dark:hover:text-white transition-colors"
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="inline-flex items-center gap-2 px-5 h-9 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-sm font-semibold text-black transition-all duration-300 hover:from-amber-400 hover:to-orange-400 hover:shadow-lg hover:shadow-amber-500/20 active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {submitting && <Loader2 className="size-4 animate-spin" />}
              {submitting ? "Adding…" : "Add stock"}
            </button>
          </DialogFooter>
        </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
