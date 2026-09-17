"use client";

/**
 * Posting to the books, and the trial balance.
 *
 * The books follow the counter by themselves every few minutes; the button is
 * for when the accountant wants today's last receipt in before reading a
 * figure. Anything that could not be posted is listed with its reason — a
 * bill that does not add up is never forced into the books.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { PostingRun, TrialBalance } from "@/lib/types/accounts";
import { drCr, financialYearStart } from "@/lib/types/accounts";
import { formatINR } from "@/lib/types/emr";
import { formatDateTime, hospitalToday } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export function BooksPanel({ canManage, onOpenLedger }: { canManage: boolean; onOpenLedger: (id: string) => void }) {
  const today = hospitalToday();
  const [from, setFrom] = useState(financialYearStart(today));
  const [to, setTo] = useState(today);
  const [runs, setRuns] = useState<PostingRun[]>([]);
  const [balance, setBalance] = useState<TrialBalance | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [recent, trial] = await Promise.all([staffApi.postingRuns(), staffApi.trialBalance(from, to)]);
      setRuns(recent);
      setBalance(trial);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The books could not be loaded.");
    }
  }, [from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  async function post(full: boolean) {
    setBusy(true);
    setError(null);
    try {
      await staffApi.postToBooks(full);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Posting failed.");
    } finally {
      setBusy(false);
    }
  }

  const last = runs[0];
  const exceptions = last?.summary.exceptions ?? [];

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-clay">{error}</p>}
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-2">
          <CardTitle>Posting to the books</CardTitle>
          {canManage && (
            <div className="flex gap-2">
              <Button size="sm" onClick={() => void post(false)} disabled={busy}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Post new entries
              </Button>
              <Button size="sm" variant="outline" onClick={() => void post(true)} disabled={busy}>
                Re-check everything
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          {!last && <p className="text-ink-muted">Nothing has been posted yet.</p>}
          {last && (
            <>
              <p>
                Last run {formatDateTime(last.started_at)} by {last.triggered_by}:{" "}
                <span className="font-medium">{last.status}</span>
                {last.error ? ` — ${last.error}` : ""}
              </p>
              <p className="text-ink-muted">
                {last.summary.posted ?? 0} posted · {last.summary.replaced ?? 0} replaced after a change ·{" "}
                {last.summary.reversed ?? 0} reversed after a cancellation · {last.summary.unchanged ?? 0} already
                correct · {last.summary.failed ?? 0} could not be posted
              </p>
            </>
          )}
          {exceptions.length > 0 && (
            <div className="rounded-lg border border-clay/30 bg-clay/5 p-3">
              <p className="mb-1 flex items-center gap-1.5 font-medium text-clay">
                <AlertTriangle className="h-4 w-4" /> Not posted — fix at the source
              </p>
              <ul className="space-y-0.5 text-xs">
                {exceptions.map((item) => (
                  <li key={`${item.source}-${item.error}`}><span className="font-medium">{item.source}:</span> {item.error}</li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-2">
          <CardTitle className="flex items-center gap-2">
            Trial balance
            {balance && (balance.balanced
              ? <Badge className="gap-1"><CheckCircle2 className="h-3 w-3" /> Balanced</Badge>
              : <Badge variant="outline" className="border-clay text-clay">Does not balance</Badge>)}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Input type="date" className="w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
            <span className="text-ink-muted">to</span>
            <Input type="date" className="w-40" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          {balance && balance.opening_difference_paise !== 0 && (
            <p className="px-4 pb-2 text-sm text-clay">
              Opening balances differ by {drCr(balance.opening_difference_paise, formatINR)}. Check the opening
              balances set on the ledgers.
            </p>
          )}
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-border bg-mint/50 text-left text-xs uppercase tracking-wide text-ink-faint">
                <th className="px-4 py-2">Ledger</th>
                <th className="px-4 py-2 text-right">Opening</th>
                <th className="px-4 py-2 text-right">Debit</th>
                <th className="px-4 py-2 text-right">Credit</th>
                <th className="px-4 py-2 text-right">Closing</th>
              </tr>
            </thead>
            <tbody>
              {balance?.rows.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-ink-muted">No entries in this period.</td></tr>
              )}
              {balance?.rows.map((row) => (
                <tr key={row.ledger_id} className="cursor-pointer border-b border-border last:border-0 hover:bg-mint/40"
                    onClick={() => onOpenLedger(row.ledger_id)}>
                  <td className="px-4 py-2">
                    <p className="font-medium">{row.name}</p>
                    <p className="text-xs text-ink-muted">{row.group_path}</p>
                  </td>
                  <td className="tabular px-4 py-2 text-right">{drCr(row.opening_paise, formatINR)}</td>
                  <td className="tabular px-4 py-2 text-right">{row.debit_paise ? formatINR(row.debit_paise) : "—"}</td>
                  <td className="tabular px-4 py-2 text-right">{row.credit_paise ? formatINR(row.credit_paise) : "—"}</td>
                  <td className="tabular px-4 py-2 text-right font-medium">{drCr(row.closing_paise, formatINR)}</td>
                </tr>
              ))}
            </tbody>
            {balance && (
              <tfoot>
                <tr className="border-t-2 border-pine/20 font-semibold">
                  <td className="px-4 py-2">Total</td>
                  <td className="tabular px-4 py-2 text-right">{drCr(balance.totals.opening_paise, formatINR)}</td>
                  <td className="tabular px-4 py-2 text-right">{formatINR(balance.totals.debit_paise)}</td>
                  <td className="tabular px-4 py-2 text-right">{formatINR(balance.totals.credit_paise)}</td>
                  <td className="tabular px-4 py-2 text-right">{drCr(balance.totals.closing_paise, formatINR)}</td>
                </tr>
              </tfoot>
            )}
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
