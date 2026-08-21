"use client";

import { useEffect } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Route-level error boundary: never show a stack trace to hospital staff. */
export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled UI error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[60vh] items-center justify-center px-5">
      <div className="max-w-md text-center">
        <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-full bg-clay/10">
          <AlertTriangle className="h-6 w-6 text-clay" />
        </div>
        <h1 className="font-display text-2xl font-semibold text-pine">
          Something went wrong
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          The page could not be displayed. Your data is safe — nothing was lost.
          Try again, and if it keeps happening, tell the IT desk the reference below.
        </p>
        {error.digest && (
          <p className="mt-3 font-mono text-xs text-ink-faint">Reference: {error.digest}</p>
        )}
        <div className="mt-6 flex justify-center gap-2">
          <Button onClick={reset}>
            <RotateCcw /> Try again
          </Button>
          <Button variant="outline" onClick={() => (window.location.href = "/dashboard")}>
            Back to dashboard
          </Button>
        </div>
      </div>
    </div>
  );
}
