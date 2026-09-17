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
import type { CashSession } from "@/lib/types/emr";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import { useToast } from "@/components/ui/toast";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const CASH_REFRESH_MS = 10000;

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
      setCashTaken(current.cash_taken_paise ?? 0);
    } catch {
      setSession(null);
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), CASH_REFRESH_MS);
    const refreshAfterPayment = () => void load();
    window.addEventListener("reception-payment-recorded", refreshAfterPayment);
    return () => {
      clearInterval(timer);
      window.removeEventListener("reception-payment-recorded", refreshAfterPayment);
    };
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
      await load();
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
      <CardHeader
        className={cn(
          "flex-row items-center gap-2 space-y-0",
          compact ? "p-3 pb-2" : "pb-3"
        )}
      >
        <Wallet className="h-3.5 w-3.5 text-pine" />
        <CardTitle className={cn(compact && "text-xs")}>
          {session ? "Your counter" : "Cash counter"}
        </CardTitle>
        {session && (
          <span className="ml-auto rounded bg-mint px-2 py-0.5 text-[11px] font-medium text-pine">
            Open
          </span>
        )}
      </CardHeader>

      <CardContent className={cn(compact && "p-3 pt-0")}>
        {session ? (
          <div className={cn(compact ? "space-y-2" : "space-y-3")}>
            <div className={cn("grid gap-2", compact ? "grid-cols-3" : "gap-3 sm:grid-cols-3")}>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-ink-faint">Float</p>
                <p className="tabular text-xs font-semibold text-ink">
                  {formatINR(session.opening_float_paise)}
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-ink-faint">Cash in</p>
                <p className="tabular text-xs font-semibold text-ink">
                  {formatINR(cashTaken)}
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wide text-ink-faint">Expected</p>
                <p className="tabular text-xs font-semibold text-pine">
                  {formatINR(expected)}
                </p>
              </div>
            </div>

            <div className={cn("rounded-lg bg-mint", compact ? "p-2" : "p-3")}>
              <label className="field-label" htmlFor="counted-cash">
                Count the drawer (₹)
              </label>
              <Input
                id="counted-cash"
                value={countedCash}
                inputMode="decimal"
                placeholder="0"
                className={cn(compact && "h-8 text-sm")}
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
                className="mt-2 w-full"
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
          <div className={cn(compact ? "space-y-2" : "space-y-3")}>
            {!compact && (
              <p className="text-xs leading-relaxed text-ink-muted">
                Open your counter at the start of the shift so the cash you take can
                be checked against the drawer at the end of it.
              </p>
            )}
            <div>
              <label className="field-label" htmlFor="opening-float">
                Opening float (₹)
              </label>
              <Input
                id="opening-float"
                value={openingFloat}
                inputMode="decimal"
                placeholder="0"
                className={cn(compact && "h-8 text-sm")}
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
