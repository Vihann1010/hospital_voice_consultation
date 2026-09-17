"use client";

/**
 * The code the nurse holds up.
 *
 * The patient is sitting in the intake room with a bag of old prescriptions.
 * The alternative to this is photocopying at the desk, or the doctor reading
 * them across a table halfway through the consultation.
 *
 * The code is not shown until it is asked for. It expires in minutes, and a
 * QR sitting on a screen all morning is one that has expired by the time
 * anybody points a phone at it — worse than no button, because it looks like
 * it should work.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, QrCode, RefreshCw, X } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { UploadLink } from "@/lib/types/emr";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function UploadQr({
  consultationId,
  className,
}: {
  consultationId: string;
  className?: string;
}) {
  const [link, setLink] = useState<UploadLink | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);

  const issue = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const found = await staffApi.createUploadLink(consultationId);
      setLink(found);
      setSecondsLeft(found.expires_in_minutes * 60);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not make a code.");
    } finally {
      setLoading(false);
    }
  }, [consultationId]);

  // Counted down on screen so the nurse can see it going stale rather than
  // discovering it has, with a patient holding up a phone.
  useEffect(() => {
    if (!link || secondsLeft <= 0) return;
    const timer = setInterval(() => setSecondsLeft((value) => value - 1), 1000);
    return () => clearInterval(timer);
  }, [link, secondsLeft]);

  const expired = Boolean(link) && secondsLeft <= 0;
  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;

  if (!link) {
    return (
      <div className={cn("rounded-xl border border-pine/10 bg-white p-4", className)}>
        <div className="flex items-start gap-2">
          <QrCode className="mt-0.5 h-4 w-4 shrink-0 text-pine" />
          <div className="min-w-0 flex-1">
            <h3 className="font-display text-sm font-semibold text-pine">
              Old reports on paper?
            </h3>
            <p className="mt-0.5 text-[11px] text-ink-muted">
              Show a code the patient scans to photograph them straight onto this
              visit.
            </p>
          </div>
        </div>
        {error && <p className="mt-2 text-[11px] text-clay">{error}</p>}
        <Button
          size="sm"
          variant="outline"
          className="mt-3 w-full"
          disabled={loading}
          onClick={() => void issue()}
        >
          {loading ? (
            <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
          ) : (
            <QrCode className="mr-1 h-3.5 w-3.5" />
          )}
          Show upload code
        </Button>
      </div>
    );
  }

  return (
    <div className={cn("rounded-xl border border-pine/10 bg-white p-4", className)}>
      <div className="flex items-center gap-2">
        <QrCode className="h-4 w-4 text-pine" />
        <h3 className="font-display text-sm font-semibold text-pine">
          Scan to add reports
        </h3>
        <button
          type="button"
          onClick={() => setLink(null)}
          className="ml-auto rounded p-1 text-ink-faint transition hover:text-clay"
          aria-label="Hide the code"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {link.unreachable_warning && (
        <p className="mt-2 flex items-start gap-1.5 rounded-md bg-clay/5 px-2 py-1.5 text-[11px] text-clay">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          {/* Worth saying before the nurse discovers it with a patient
              waiting: a phone resolves "localhost" to itself, so this code
              opens nothing until the hospital sets a reachable address. */}
          This code points at <code>localhost</code>, which a phone cannot open. Set
          the hospital&apos;s public address before using this at the desk.
        </p>
      )}

      <div className="mt-3 flex flex-col items-center">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={link.qr_data_uri}
          alt="QR code to upload reports from a phone"
          className={cn(
            "h-44 w-44 rounded-lg border border-border bg-white p-1",
            expired && "opacity-30 grayscale"
          )}
        />
        {expired ? (
          <p className="mt-2 text-[11px] font-medium text-clay">
            This code has expired.
          </p>
        ) : (
          <p className="tabular mt-2 text-[11px] text-ink-faint">
            Works for another {minutes}:{String(seconds).padStart(2, "0")}
          </p>
        )}
      </div>

      <Button
        size="sm"
        variant={expired ? "default" : "ghost"}
        className="mt-2 w-full text-xs"
        disabled={loading}
        onClick={() => void issue()}
      >
        <RefreshCw className="mr-1 h-3 w-3" />
        {expired ? "Get a fresh code" : "Replace this code"}
      </Button>
    </div>
  );
}
