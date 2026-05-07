"use client";

import { useState } from "react";
import { Plus, X, Filter as FilterIcon } from "lucide-react";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import type { ColumnDef } from "@/lib/tables";
import type { Filter } from "@/lib/query-builder";

const OP_OPTIONS_TEXT: { value: Filter["op"]; label: string }[] = [
  { value: "eq",       label: "equals"        },
  { value: "ne",       label: "not equal"     },
  { value: "contains", label: "contains"      },
  { value: "starts",   label: "starts with"   },
  { value: "ends",     label: "ends with"     },
];

const OP_OPTIONS_NUMERIC: { value: Filter["op"]; label: string }[] = [
  { value: "eq", label: "="  },
  { value: "ne", label: "≠"  },
  { value: "lt", label: "<"  },
  { value: "le", label: "≤"  },
  { value: "gt", label: ">"  },
  { value: "ge", label: "≥"  },
];

function isNumericColumn(col: ColumnDef): boolean {
  return (
    col.type === "number" ||
    col.type === "decimal" ||
    col.type === "datetime_ms" ||
    col.type === "datetime_double_seconds" ||
    col.type === "datetime_decimal_seconds"
  );
}

const fieldClasses =
  "h-10 rounded-xl border border-zinc-900/10 dark:border-white/10 bg-white/60 dark:bg-white/[0.03] text-sm text-zinc-900 dark:text-zinc-100 outline-none transition-all duration-200 focus:border-amber-500/50 focus:ring-2 focus:ring-amber-500/20 placeholder:text-zinc-400 dark:placeholder:text-zinc-600";

export function FilterBar({
  columns,
  filters,
  onChange,
}: {
  columns: ColumnDef[];
  filters: Filter[];
  onChange: (filters: Filter[]) => void;
}) {
  const [draftCol, setDraftCol] = useState<string>(columns[0]?.key ?? "");
  const [draftOp, setDraftOp]   = useState<Filter["op"]>("eq");
  const [draftVal, setDraftVal] = useState<string>("");

  const draftColumn = columns.find((c) => c.key === draftCol) ?? columns[0];
  const numeric = draftColumn ? isNumericColumn(draftColumn) : false;
  const opOptions = numeric ? OP_OPTIONS_NUMERIC : OP_OPTIONS_TEXT;

  function addFilter() {
    if (!draftVal.trim()) return;
    const value = numeric ? Number(draftVal) : draftVal;
    if (numeric && !Number.isFinite(value as number)) return;
    onChange([...filters, { column: draftCol, op: draftOp, value: value as string | number }]);
    setDraftVal("");
  }

  function removeFilter(idx: number) {
    onChange(filters.filter((_, i) => i !== idx));
  }

  function clearAll() {
    onChange([]);
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <FilterIcon className="size-4 text-zinc-400 dark:text-zinc-500 shrink-0" />

        <Select value={draftCol} onValueChange={(v) => v && setDraftCol(v)}>
          <SelectTrigger className={`${fieldClasses} w-44 px-3`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {columns.map((c) => (
              <SelectItem key={c.key} value={c.key}>{c.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={draftOp} onValueChange={(v) => v && setDraftOp(v as Filter["op"])}>
          <SelectTrigger className={`${fieldClasses} w-36 px-3`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {opOptions.map((o) => (
              <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Input
          value={draftVal}
          onChange={(e) => setDraftVal(e.target.value)}
          placeholder="value"
          className={`${fieldClasses} w-44 px-3`}
          onKeyDown={(e) => {
            if (e.key === "Enter") addFilter();
          }}
        />

        <button
          onClick={addFilter}
          className="inline-flex items-center gap-1.5 px-4 h-10 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-sm font-semibold text-black transition-all duration-300 hover:from-amber-400 hover:to-orange-400 hover:shadow-lg hover:shadow-amber-500/20 active:scale-[0.97]"
        >
          <Plus className="size-3.5" />
          Add
        </button>

        {filters.length > 0 && (
          <button
            onClick={clearAll}
            className="px-3 h-10 rounded-xl text-xs text-zinc-500 hover:text-zinc-900 dark:hover:text-white transition-colors"
          >
            Clear
          </button>
        )}
      </div>

      {filters.length > 0 && (
        <div className="flex flex-wrap gap-2 pl-6">
          {filters.map((f, idx) => {
            const col = columns.find((c) => c.key === f.column);
            return (
              <button
                key={idx}
                onClick={() => removeFilter(idx)}
                className="group inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-500/10 border border-amber-500/20 text-xs text-amber-700 dark:text-amber-300 transition-all duration-300 hover:bg-amber-500/20 hover:border-amber-500/40"
                title="click to remove"
              >
                <span className="opacity-80">{col?.label ?? f.column}</span>
                <span className="font-mono opacity-90">{f.op}</span>
                <span className="font-mono font-semibold">{String(f.value)}</span>
                <X className="size-3 opacity-60 group-hover:opacity-100" />
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
