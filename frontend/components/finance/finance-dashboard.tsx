"use client";

/**
 * Finance: the day's money and the drawer.
 *
 * Billed and collected are shown as separate figures throughout, never netted.
 * They diverge whenever a patient part-pays, a bill goes to insurance, or a
 * refund is issued — and a screen that conflates them makes a day look
 * balanced when it is not.
 */
import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Banknote, CreditCard, RefreshCw, TrendingUp, } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { CollectionSummary } from "@/lib/types/emr";
import { formatINR } from "@/lib/types/emr";
import { DEPARTMENT_FULL_LABEL } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const MODE_LABELS: Record<string, string> = {
  cash: "Cash",
  upi: "UPI",
  card: "Card",
  net_banking: "Net banking",
  insurance: "Insurance / TPA",
  waiver: "Waived",
};

function Stat({
  label, value, hint, tone = "default", index,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "accent" | "warn";
  index: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.04 }}
    >
      <Card className={cn(tone === "accent" && "bg-pine text-mint")}>
        <CardContent className="p-5">
          <p className={cn(
            "text-[11px] uppercase tracking-wide",
            tone === "accent" ? "text-mint/60" : "text-ink-faint"
          )}>
            {label}
          </p>
          <p className={cn(
            "tabular mt-1 font-display text-2xl font-semibold",
            tone === "accent" ? "text-mint" : tone === "warn" ? "text-clay" : "text-pine"
          )}>
            {value}
          </p>
          {hint && (
            <p className={cn(
              "mt-1 text-xs",
              tone === "accent" ? "text-mint/60" : "text-ink-muted"
            )}>
              {hint}
            </p>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

export function FinanceDashboard() {
  const [summary, setSummary] = useState<CollectionSummary | null>(null);
  const [on, setOn] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [error, setError] = useState<string | null>(null);


  const load = useCallback(async () => {
    try {
      setSummary(await staffApi.collections(on));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the day's figures.");
    }
  }, [on]);

  useEffect(() => {
    void load();
  }, [load]);





  return (
    <div className="space-y-6">
      {error && <Card className="border-clay/30 bg-clay/5 p-4 text-sm text-clay">{error}</Card>}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Input
          type="date"
          value={on}
          onChange={(event) => setOn(event.target.value)}
          className="w-auto"
          aria-label="Date"
        />
        <Button variant="outline" size="sm" onClick={() => void load()}>
          <RefreshCw /> Refresh
        </Button>
      </div>

      {summary === null ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="h-28 rounded-xl" />
          ))}
        </div>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat index={0} label="Collected" tone="accent"
                  value={formatINR(summary.collected_paise)}
                  hint={`${summary.patient_count} patients`} />
            <Stat index={1} label="Billed"
                  value={formatINR(summary.billed_paise)}
                  hint={`${summary.invoice_count} invoices`} />
            <Stat index={2} label="Outstanding"
                  tone={summary.outstanding_paise > 0 ? "warn" : "default"}
                  value={formatINR(summary.outstanding_paise)}
                  hint="Billed but not yet paid" />
            <Stat index={3} label="Refunded"
                  tone={summary.refunded_paise > 0 ? "warn" : "default"}
                  value={formatINR(summary.refunded_paise)}
                  hint={`Discounts ${formatINR(summary.discount_paise)}`} />
          </div>

          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
                <CreditCard className="h-4 w-4 text-pine" />
                <CardTitle>How it was paid</CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(summary.by_mode).length === 0 ? (
                  <p className="py-4 text-sm text-ink-faint">Nothing collected on this day.</p>
                ) : (
                  <ul className="space-y-2">
                    {Object.entries(summary.by_mode)
                      .sort((a, b) => b[1] - a[1])
                      .map(([mode, amount]) => {
                        const share = summary.collected_paise
                          ? Math.round((amount / summary.collected_paise) * 100)
                          : 0;
                        return (
                          <li key={mode}>
                            <div className="flex items-center justify-between text-sm">
                              <span className="text-ink">{MODE_LABELS[mode] ?? mode}</span>
                              <span className="tabular font-medium text-ink">
                                {formatINR(amount)}
                              </span>
                            </div>
                            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-mint">
                              <div className="h-full rounded-full bg-pine"
                                   style={{ width: `${Math.max(share, 2)}%` }} />
                            </div>
                          </li>
                        );
                      })}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex-row items-center gap-2 space-y-0 pb-3">
                <TrendingUp className="h-4 w-4 text-pine" />
                <CardTitle>By department</CardTitle>
              </CardHeader>
              <CardContent>
                {Object.keys(summary.by_department).length === 0 ? (
                  <p className="py-4 text-sm text-ink-faint">No billing on this day.</p>
                ) : (
                  <ul className="space-y-2.5">
                    {Object.entries(summary.by_department).map(([department, amount]) => (
                      <li key={department} className="flex items-center justify-between text-sm">
                        <span className="capitalize text-ink">
                          {DEPARTMENT_FULL_LABEL[department] ?? department}
                        </span>
                        <span className="tabular font-medium text-ink">
                          {formatINR(amount)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </>
      )}

      <p className="text-xs text-ink-muted">
        Cash reconciliation has moved to the reception terminal, where the
        cashier who holds the drawer can open and close their own shift.
      </p>
    </div>
  );
}
