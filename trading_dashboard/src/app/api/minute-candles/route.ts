import { NextRequest } from "next/server";
import { paginatedTableHandler } from "@/lib/handlers";
import {
  MINUTE_CANDLES_COLUMNS,
  MINUTE_CANDLES_COLUMN_WHITELIST,
  MINUTE_CANDLES_DEFAULT_SORT,
  MINUTE_CANDLES_TABLE,
  dbColumnKeys,
} from "@/lib/tables";

export async function GET(req: NextRequest) {
  return paginatedTableHandler(req, {
    table: MINUTE_CANDLES_TABLE,
    columnList: dbColumnKeys(MINUTE_CANDLES_COLUMNS),
    columnWhitelist: MINUTE_CANDLES_COLUMN_WHITELIST,
    defaultSort: MINUTE_CANDLES_DEFAULT_SORT,
  });
}
