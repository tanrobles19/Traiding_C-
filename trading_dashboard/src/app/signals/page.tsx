"use client";

import { TablePage } from "@/components/TablePage";
import { SymbolBarChart } from "@/components/SymbolBarChart";
import { SIGNALS_COLUMNS } from "@/lib/tables";

type SignalRow = {
  symbol: string | null;
  timestamp: number | null;
  close: number | string | null;
  volume: number | null;
};

export default function SignalsPage() {
  return (
    <TablePage<SignalRow>
      title="Trade Signals — buy per second"
      description="TradeSignalsBuyPerSecond"
      apiPath="/api/signals"
      clearEndpoint="/api/signals/clear"
      columns={SIGNALS_COLUMNS}
      renderChart={(rows) => (
        <SymbolBarChart rows={rows} title="Top symbols on this page" />
      )}
    />
  );
}
