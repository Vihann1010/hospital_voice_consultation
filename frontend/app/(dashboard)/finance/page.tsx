"use client";

import { FormEvent, useState } from "react";
import { PageHeader } from "@/components/dashboard/page-header";
import { FinanceDashboard } from "@/components/finance/finance-dashboard";
import { staffApi } from "@/lib/staffApi";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";

export default function FinancePage() {
  const [unlocked, setUnlocked] = useState(
    () => typeof window !== "undefined" && Boolean(sessionStorage.getItem("finance_unlock"))
  );
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await staffApi.verifyFinancePin(pin);
      sessionStorage.setItem("finance_unlock", result.token);
      setUnlocked(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid finance PIN.");
      setPin("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Finance"
        subtitle="Collections, payment modes and cash reconciliation."
      />
      {unlocked ? (
        <FinanceDashboard />
      ) : (
        <Card className="max-w-md">
          <CardContent className="p-6">
            <form onSubmit={unlock} className="space-y-4">
              <div>
                <h2 className="font-display text-lg font-semibold text-pine">Finance PIN</h2>
                <p className="mt-1 text-sm text-ink-muted">Enter the four-digit PIN to continue.</p>
              </div>
              <Input
                value={pin}
                onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 4))}
                inputMode="numeric"
                pattern="[0-9]{4}"
                maxLength={4}
                autoFocus
                aria-label="Finance PIN"
              />
              {error && <p className="text-sm text-clay">{error}</p>}
              <Button type="submit" disabled={busy || pin.length !== 4}>
                {busy ? "Checking..." : "Open finance"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
