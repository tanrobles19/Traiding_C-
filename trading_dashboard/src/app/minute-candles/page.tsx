"use client";

import { TablePage } from "@/components/TablePage";
import { MINUTE_CANDLES_COLUMNS } from "@/lib/tables";

type MinuteCandleRow = {
  stock_symbol: string | null;
  timestamp: string | null;
  volume: number | null;
  close_price: number | null;
};

export default function MinuteCandlesPage() {
  return (
    <TablePage<MinuteCandleRow>
      title="Minute Candlesticks"
      description="minute_candlesticks — per-symbol per-minute snapshots written at minute rollover. Filter by Symbol in the column header."
      apiPath="/api/minute-candles"
      columns={MINUTE_CANDLES_COLUMNS}
    />
  );
}
