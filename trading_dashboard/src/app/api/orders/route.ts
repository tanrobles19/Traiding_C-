import { NextRequest } from "next/server";
import { paginatedTableHandler } from "@/lib/handlers";
import {
  ORDERS_COLUMNS,
  ORDERS_COLUMN_WHITELIST,
  ORDERS_DEFAULT_SORT,
  ORDERS_TABLE,
  dbColumnKeys,
} from "@/lib/tables";

export async function GET(req: NextRequest) {
  return paginatedTableHandler(req, {
    table: ORDERS_TABLE,
    columnList: dbColumnKeys(ORDERS_COLUMNS),
    columnWhitelist: ORDERS_COLUMN_WHITELIST,
    defaultSort: ORDERS_DEFAULT_SORT,
  });
}
