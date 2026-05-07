"use client";

import { TablePage } from "@/components/TablePage";
import { RV_COLUMNS } from "@/lib/tables";

type RvRow = {
  id: number | null;
  symbol: string | null;
  hour: number | null;
  amPm: string | null;
  relative_volume: number | null;
};

export default function RelativeVolumePage() {
  return (
    <TablePage<RvRow>
      title="Relative Volume — hourly baselines"
      description="RelativeVolumeRatioHour"
      apiPath="/api/rv"
      columns={RV_COLUMNS}
    />
  );
}
