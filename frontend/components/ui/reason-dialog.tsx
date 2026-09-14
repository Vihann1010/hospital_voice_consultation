"use client";

/**
 * "Are you sure, and why?"
 *
 * Every destructive action at the counter — cancelling a bill, striking a
 * receipt, cancelling an appointment — needs a written reason recorded
 * against the person doing it. A native `window.prompt` would do the job and
 * was the first thing here, but it is wrong in three ways that matter: it is
 * unstyled in the middle of a hospital application and reads as a fault, it
 * cannot show the API's refusal in context, and it blocks the page.
 *
 * This asks the same question, states plainly what is about to happen, and
 * keeps the error where the reason was typed so the clerk can correct it and
 * try again without losing what they wrote.
 */
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export interface ReasonRequest {
  title: string;
  /** What this will actually do, in the clerk's language. */
  detail?: string;
  confirmLabel: string;
  destructive?: boolean;
  /** Resolve to run the action; throwing shows the message inline. */
  run: (reason: string) => Promise<unknown>;
}

export function ReasonDialog({
  request,
  onClose,
  onDone,
}: {
  request: ReasonRequest | null;
  onClose: () => void;
  onDone?: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setReason("");
    setError(null);
    setBusy(false);
    if (request) {
      // Focused after paint, so the clerk types the reason rather than
      // hunting for the field.
      const timer = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(timer);
    }
  }, [request]);

  if (!request) return null;

  const ready = reason.trim().length >= 3;

  async function submit() {
    if (!ready || !request) return;
    setBusy(true);
    setError(null);
    try {
      await request.run(reason.trim());
      onDone?.();
      onClose();
    } catch (err) {
      // Shown here rather than as a toast: the API refuses out-of-order
      // corrections with a sentence explaining what to do first, and that
      // belongs next to the thing being attempted.
      setError(err instanceof Error ? err.message : "That did not go through.");
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/25 p-3"
      role="dialog"
      aria-modal="true"
      aria-label={request.title}
      onClick={() => !busy && onClose()}
    >
      <div
        className="w-full max-w-sm space-y-3 rounded-2xl border border-pine/10 bg-white p-4 shadow-lift"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start gap-2">
          {request.destructive && (
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-clay" />
          )}
          <div>
            <h3 className="font-display text-sm font-semibold text-pine">
              {request.title}
            </h3>
            {request.detail && (
              <p className="mt-0.5 text-[11px] text-ink-muted">{request.detail}</p>
            )}
          </div>
        </div>

        <div>
          <label
            className="text-[11px] uppercase tracking-wide text-ink-faint"
            htmlFor="reason-dialog-input"
          >
            Reason
          </label>
          <Input
            id="reason-dialog-input"
            ref={inputRef}
            value={reason}
            disabled={busy}
            onChange={(event) => setReason(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && ready) {
                event.preventDefault();
                void submit();
              }
              if (event.key === "Escape" && !busy) {
                // Stopped here, not merely handled. React flushes this close
                // synchronously, so by the time the global keyboard listener
                // on `window` runs, the dialog is already out of the DOM and
                // its "is a modal open" check passes — firing the global
                // Escape shortcut and navigating the clerk off the screen
                // they were only trying to back out of.
                event.preventDefault();
                event.stopPropagation();
                event.nativeEvent.stopImmediatePropagation();
                onClose();
              }
            }}
            placeholder="Recorded against your name"
            className="mt-1 h-9 text-sm"
          />
        </div>

        {error && <p className="text-xs text-clay">{error}</p>}

        <div className="flex gap-2">
          <Button variant="ghost" size="sm" disabled={busy} onClick={onClose}>
            Keep as it is
          </Button>
          <Button
            size="sm"
            className="flex-1"
            disabled={!ready || busy}
            onClick={() => void submit()}
          >
            {busy && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
            {request.confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
