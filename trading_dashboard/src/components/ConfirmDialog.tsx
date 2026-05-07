"use client";

import { useState, cloneElement, isValidElement, type ReactElement, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

// Reusable destructive-confirm dialog. Wraps a trigger element (a button,
// usually) and awaits a user-supplied async action before closing.
//
// We control the dialog ourselves and clone the trigger to inject an
// onClick that opens it — base-ui's AlertDialogTrigger uses a `render`
// prop pattern that's awkward when the parent doesn't know what kind of
// element to render.
export function ConfirmDialog({
  trigger,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = true,
  onConfirm,
}: {
  trigger: ReactElement<{ onClick?: (e: React.MouseEvent) => void }>;
  title: string;
  description: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => Promise<void> | void;
}) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  const confirmClasses = destructive
    ? "inline-flex items-center gap-2 px-5 py-2 rounded-xl bg-red-500 text-white text-sm font-semibold transition-all duration-300 hover:bg-red-600 active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed"
    : "inline-flex items-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-black text-sm font-semibold transition-all duration-300 hover:from-amber-400 hover:to-orange-400 active:scale-[0.97] disabled:opacity-50 disabled:cursor-not-allowed";

  async function handleConfirm() {
    setLoading(true);
    try {
      await onConfirm();
      setOpen(false);
    } finally {
      setLoading(false);
    }
  }

  // Clone the trigger to inject an onClick that opens the dialog.
  const wrappedTrigger = isValidElement(trigger)
    ? cloneElement(trigger, {
        onClick: (e: React.MouseEvent) => {
          trigger.props.onClick?.(e);
          if (!e.defaultPrevented) setOpen(true);
        },
      })
    : trigger;

  return (
    <>
      {wrappedTrigger}
      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{title}</AlertDialogTitle>
            <AlertDialogDescription>{description}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={loading}>{cancelLabel}</AlertDialogCancel>
            <AlertDialogAction
              disabled={loading}
              onClick={(e) => {
                e.preventDefault();
                handleConfirm();
              }}
              className={confirmClasses}
            >
              {loading && <Loader2 className="size-4 animate-spin" />}
              {confirmLabel}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
