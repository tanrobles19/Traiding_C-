import { NextRequest } from "next/server";
import { paginatedTableHandler } from "@/lib/handlers";
import {
  RV_COLUMNS,
  RV_COLUMN_WHITELIST,
  RV_DEFAULT_SORT,
  RV_TABLE,
  dbColumnKeys,
} from "@/lib/tables";

export async function GET(req: NextRequest) {
  return paginatedTableHandler(req, {
    table: RV_TABLE,
    columnList: dbColumnKeys(RV_COLUMNS),
    columnWhitelist: RV_COLUMN_WHITELIST,
    defaultSort: RV_DEFAULT_SORT,
  });
}
