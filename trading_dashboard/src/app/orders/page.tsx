"use client";

import { TablePage } from "@/components/TablePage";
import { SymbolBarChart } from "@/components/SymbolBarChart";
import { ORDERS_COLUMNS } from "@/lib/tables";

type OrderRow = {
  id: number | null;
  symbol: string | null;
  status: string | null;
  orderType: string | null;
};

export default function OrdersPage() {
  return (
    <TablePage<OrderRow>
      title="Orders"
      description="Orders"
      apiPath="/api/orders"
      clearEndpoint="/api/orders/clear"
      columns={ORDERS_COLUMNS}
      renderChart={(rows) => (
        <SymbolBarChart rows={rows} title="Top symbols on this page" />
      )}
    />
  );
}
