"use client";

import { Trash2 } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { ConfirmDialog } from "@/components/ConfirmDialog";

// Row-action button used by AG Grid. Given the row's id and a label,
// shows a trash icon. Click → confirm dialog → DELETE /api/<resource>/<id>
// → invalidate the table query so the row disappears.
export function RowDeleteButton({
  apiPath,
  id,
  label,
  invalidateKeys = [],
}: {
  apiPath: string;
  id: number | string;
  label: string;
  invalidateKeys?: unknown[][];
}) {
  const queryClient = useQueryClient();

  async function onConfirm() {
    const r = await fetch(`${apiPath}/${id}`, { method: "DELETE" });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.error ?? `delete failed (${r.status})`);
    }
    for (const key of invalidateKeys) {
      await queryClient.invalidateQueries({ queryKey: key });
    }
  }

  return (
    <ConfirmDialog
      title={`Remove ${label}?`}
      description={
        <span>
          This deletes <span className="font-mono">{label}</span> from the master Stocks registry.
        </span>
      }
      confirmLabel="Remove"
      onConfirm={onConfirm}
      trigger={
        <button
          className="inline-flex items-center justify-center size-7 rounded-md text-zinc-500 hover:text-red-600 dark:hover:text-red-400 hover:bg-red-500/10 transition-colors"
          title="Remove from registry"
          aria-label={`Remove ${label}`}
        >
          <Trash2 className="size-3.5" />
        </button>
      }
    />
  );
}
