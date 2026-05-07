"use client";

import { TablePage } from "@/components/TablePage";
import { AddStockDialog } from "@/components/AddStockDialog";
import { RowDeleteButton } from "@/components/RowDeleteButton";
import { STOCKS_COLUMNS } from "@/lib/tables";

type StockRow = {
  id: number | null;
  ticker: string | null;
  close: number | string | null;
  float_value: number | null;
  short_percent_float: number | null;
  avg_month_volume: number | null;
  shares_outstanding: number | null;
  shares_short: number | null;
};

export default function StocksPage() {
  return (
    <TablePage<StockRow>
      title="Stocks — symbol registry"
      description="Stocks"
      apiPath="/api/stocks"
      columns={STOCKS_COLUMNS}
      toolbarExtra={<AddStockDialog apiPath="/api/stocks" />}
      rowAction={{
        width: 56,
        render: (row) =>
          row.id != null ? (
            <RowDeleteButton
              apiPath="/api/stocks"
              id={row.id}
              label={row.ticker ?? `id=${row.id}`}
              invalidateKeys={[["/api/stocks"], ["stats"]]}
            />
          ) : null,
      }}
    />
  );
}
