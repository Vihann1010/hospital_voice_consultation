"use client";

import { BillCorrections } from "@/components/reception/bill-corrections";
import { useAuth } from "@/components/dashboard/auth-provider";

export default function BillsPage() {
  const { user } = useAuth();
  // Cancelling and reinstating are the counter's escalation path. Reception
  // can find and reprint any bill; undoing one needs a supervisor. The API
  // enforces this regardless — hiding the buttons only avoids offering an
  // action that would come back 403.
  const canCorrect = user?.role === "admin" || user?.role === "supervisor";

  return (
    <div>
      <div className="mb-5">
        <h1 className="font-display text-2xl font-semibold text-pine">Bills</h1>
        <p className="mt-1 text-sm text-ink-muted">
          Find a past bill to reprint it, or to correct what was entered.
        </p>
      </div>
      <BillCorrections canCorrect={canCorrect} />
    </div>
  );
}
