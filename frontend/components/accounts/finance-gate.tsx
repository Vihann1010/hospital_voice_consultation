"use client";

/**
 * The finance PIN, asked before any money screen.
 *
 * The unlock it buys lasts thirty minutes. When the server refuses it, the
 * API client forgets it and fires FINANCE_LOCKED_EVENT, and the gate closes
 * again — so an expired unlock asks for the PIN rather than leaving a money
 * screen stuck on "Finance PIN required".
 */
import { FormEvent, useEffect, useState } from "react";
import { FINANCE_LOCKED_EVENT, FINANCE_UNLOCK_KEY, staffApi } from "@/lib/staffApi";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function FinanceGate({
  children,
  prompt = "Enter the four-digit PIN to open the books.",
  action = "Open the books",
}: {
  children: React.ReactNode;
  prompt?: string;
  action?: string;
}) {
  const [unlocked, setUnlocked] = useState(
    () => typeof window !== "undefined" && Boolean(sessionStorage.getItem(FINANCE_UNLOCK_KEY))
  );
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    const lock = () => {
      setUnlocked(false);
      setExpired(true);
    };
    window.addEventListener(FINANCE_LOCKED_EVENT, lock);
    return () => window.removeEventListener(FINANCE_LOCKED_EVENT, lock);
  }, []);
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function unlock(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await staffApi.verifyFinancePin(pin);
      sessionStorage.setItem(FINANCE_UNLOCK_KEY, result.token);
      setExpired(false);
      setPin("");
      setUnlocked(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid finance PIN.");
      setPin("");
    } finally {
      setBusy(false);
    }
  }

  if (unlocked) return <>{children}</>;
  return (
    <Card className="max-w-md">
      <CardContent className="p-6">
        <form onSubmit={unlock} className="space-y-4">
          <div>
            <h2 className="font-display text-lg font-semibold text-pine">Finance PIN</h2>
            <p className="mt-1 text-sm text-ink-muted">
              {expired ? "The finance screens locked again after thirty minutes. " : ""}
              {prompt}
            </p>
          </div>
          <Input value={pin} inputMode="numeric" maxLength={4} autoFocus aria-label="Finance PIN"
                 onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 4))} />
          {error && <p className="text-sm text-clay">{error}</p>}
          <Button type="submit" disabled={busy || pin.length !== 4}>{busy ? "Checking..." : action}</Button>
        </form>
      </CardContent>
    </Card>
  );
}
