import { NextRequest } from "next/server";
import { paginatedTableHandler } from "@/lib/handlers";
import {
  RAW_TRADES_COLUMNS,
  RAW_TRADES_COLUMN_WHITELIST,
  RAW_TRADES_DEFAULT_SORT,
  RAW_TRADES_TABLE,
  dbColumnKeys,
} from "@/lib/tables";

export async function GET(req: NextRequest) {
  return paginatedTableHandler(req, {
    table:           RAW_TRADES_TABLE,
    columnList:      dbColumnKeys(RAW_TRADES_COLUMNS),
    columnWhitelist: RAW_TRADES_COLUMN_WHITELIST,
    defaultSort:     RAW_TRADES_DEFAULT_SORT,
  });
}
