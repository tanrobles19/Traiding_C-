import { NextRequest } from "next/server";
import { paginatedTableHandler } from "@/lib/handlers";
import {
  RAW_QUOTES_COLUMNS,
  RAW_QUOTES_COLUMN_WHITELIST,
  RAW_QUOTES_DEFAULT_SORT,
  RAW_QUOTES_TABLE,
  dbColumnKeys,
} from "@/lib/tables";

export async function GET(req: NextRequest) {
  return paginatedTableHandler(req, {
    table:           RAW_QUOTES_TABLE,
    columnList:      dbColumnKeys(RAW_QUOTES_COLUMNS),
    columnWhitelist: RAW_QUOTES_COLUMN_WHITELIST,
    defaultSort:     RAW_QUOTES_DEFAULT_SORT,
  });
}
