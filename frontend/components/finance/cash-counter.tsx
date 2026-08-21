"use client";

/**
 * The cashier's drawer: open a shift, close it, reconcile.
 *
 * This lives on the reception terminal rather than the finance screen because
 * it is the cashier's own float, counted by the person sitting at the counter.
 * Hospital-wide revenue stays on the finance screen, where the permission
 * model already puts it — a clerk reconciles their drawer, they do not see
 * what the hospital took today.
 *
 * Only cash is counted here. Card and UPI settle through the bank and are
 * reconciled against statements, not against a drawer.
 */
import { useCallback, useEffect, useState } from "react";
import { IndianRupee, Loader2, Lock, Wallet } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { CashSession } from "@/lib/emrTypes";
import { formatINR, rupeesToPaise } from "@/lib/emrTypes";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function CashCounter({ compact = false }: { compact?: boolean }) {
  const toast = useToast();
  const [session, setSession] = useState<CashSession | null>(null);
  const [cashTaken, setCashTaken] = useState(0);
  const [openingFloat, setOpeningFloat] = useState("");
  const [countedCash, setCountedCash] = useState("");
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const current = await staffApi.currentCashSession();
      setSession(current.session);
      // The day's cash figure comes from the collections summary; a cashier
      // needs it to know what the drawer *should* hold.
      try {
        const summary = await staffApi.collections();
        setCashTaken(summary.by_mode?.cash ?? 0);
      } catch {
        // Collections is management-only. A clerk without that permission
        // still gets a working open/close, just without the expected figure.
        setCashTaken(0);
      }
    } catch {
      setSession(null);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function openSession() {
    setBusy(true);
    try {
      const created = await staffApi.openCashSession({
        opening_float_paise: rupeesToPaise(openingFloat || "0"),
      });
      setSession(created);
      setOpeningFloat("");
      toast.success("Counter opened", `Float ${formatINR(created.opening_float_paise)}`);
    } catch (err) {
      toast.error(
        "Could not open the counter",
        err instanceof Error ? err.message : undefined
      );
    } finally {
      setBusy(false);
    }
  }

  async function closeSession() {
    if (!session) return;
    setBusy(true);
    try {
      const result = await staffApi.closeCashSession(session.id, {
        counted_cash_paise: rupeesToPaise(countedCash || "0"),
      });
      setSession(null);
      setCountedCash("");
      const variance = result.session.variance_paise ?? 0;
      if (variance === 0) {
        toast.success("Counter closed", "The drawer reconciles exactly.");
      } else {
        toast.error(
          variance > 0 ? "Closed — drawer over" : "Closed — drawer short",
          `Difference of ${formatINR(Math.abs(variance))}. This has been recorded.`
        );
      }
      await load();
    } catch (err) {
      toast.error(
        "Could not close the counter",
        err instanceof Error ? err.message : undefined
      );
    } finally {
      setBusy(false);
    }
  }

  const expected = (session?.opening_float_paise ?? 0) + cashTaken;
  const counted = rupeesToPaise(countedCash || "0");
  const variance = countedCash ? counted - expected : null;

  if (!loaded) return null;

  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
        <Wallet className="h-4 w-4 text-pine" />
        <CardTitle>{session ? "Your counter" : "Cash counter"}</CardTitle>
        {session && (
          <span className="ml-auto rounded bg-mint px-2 py-0.5 text-[11px] font-medium text-pine">
            Open
          </span>
        )}
      </CardHeader>

      <CardContent>
        {session ? (
          <div className="space-y-3">
            <div className={cn("grid gap-3", compact ? "grid-cols-3" : "sm:grid-cols-3")}>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-ink-faint">Float</p>
                <p className="tabular text-sm font-semibold text-ink">
                  {formatINR(session.opening_float_paise)}
                </p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-ink-faint">Cash in</p>
                <p className="tabular text-sm font-semibold text-ink">
                  {formatINR(cashTaken)}
                </p>
              </div>
              <div>
                <p className="text-[11px] uppercase tracking-wide text-ink-faint">Expected</p>
                <p className="tabular text-sm font-semibold text-pine">
                  {formatINR(expected)}
                </p>
              </div>
            </div>

            <div className="rounded-lg bg-mint p-3">
              <label className="field-label" htmlFor="counted-cash">
                Count the drawer (₹)
              </label>
              <Input
                id="counted-cash"
                value={countedCash}
                inputMode="decimal"
                placeholder="0"
                onChange={(event) => setCountedCash(event.target.value)}
              />
              {variance !== null && (
                <p className={cn(
                  "mt-2 text-xs font-medium",
                  variance === 0 ? "text-pine" : "text-clay"
                )}>
                  {variance === 0
                    ? "Reconciles exactly."
                    : variance > 0
                      ? `Over by ${formatINR(variance)} — will be recorded.`
                      : `Short by ${formatINR(Math.abs(variance))} — will be recorded.`}
                </p>
              )}
              <Button
                className="mt-3 w-full"
                size="sm"
                onClick={closeSession}
                disabled={busy || !countedCash}
              >
                {busy ? <Loader2 className="animate-spin" /> : <Lock />}
                Close counter
              </Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-xs leading-relaxed text-ink-muted">
              Open your counter at the start of the shift so the cash you take can
              be checked against the drawer at the end of it.
            </p>
            <div>
              <label className="field-label" htmlFor="opening-float">
                Opening float (₹)
              </label>
              <Input
                id="opening-float"
                value={openingFloat}
                inputMode="decimal"
                placeholder="0"
                onChange={(event) => setOpeningFloat(event.target.value)}
              />
            </div>
            <Button className="w-full" size="sm" onClick={openSession} disabled={busy}>
              {busy ? <Loader2 className="animate-spin" /> : <IndianRupee />}
              Open counter
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
