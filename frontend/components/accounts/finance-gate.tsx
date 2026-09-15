"use client";

/** The finance PIN, asked once per browser session, before any money screen. */
import { FormEvent, useState } from "react";
import { staffApi } from "@/lib/staffApi";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function FinanceGate({ children }: { children: React.ReactNode }) {
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

  if (unlocked) return <>{children}</>;
  return (
    <Card className="max-w-md">
      <CardContent className="p-6">
        <form onSubmit={unlock} className="space-y-4">
          <div>
            <h2 className="font-display text-lg font-semibold text-pine">Finance PIN</h2>
            <p className="mt-1 text-sm text-ink-muted">Enter the four-digit PIN to open the books.</p>
          </div>
          <Input value={pin} inputMode="numeric" maxLength={4} autoFocus aria-label="Finance PIN"
                 onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 4))} />
          {error && <p className="text-sm text-clay">{error}</p>}
          <Button type="submit" disabled={busy || pin.length !== 4}>{busy ? "Checking..." : "Open the books"}</Button>
        </form>
      </CardContent>
    </Card>
  );
}
