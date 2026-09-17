"use client";

/**
 * Consultant payouts.
 *
 * Each consultant's share and the services it applies to are set here. A
 * payout is previewed from the bills, then approved — which locks the bills it
 * counted — then paid, with TDS if deducted. Bills not fully paid wait for a
 * later run, and a refund on a bill already paid out is taken back on the
 * next payout.
 */
import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { Payout, PayoutOptions, PayoutPreview } from "@/lib/types/accounts";
import { CATEGORY_LABEL, PAY_MODE_LABEL, financialYearStart } from "@/lib/types/accounts";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import { formatDate, formatDateTime, hospitalToday } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SELECT = "h-9 rounded-md border border-border bg-white px-2 text-sm text-ink";

interface Terms { percent: string; categories: string[] }

export function PayoutsPanel({ canManage }: { canManage: boolean }) {
  const today = hospitalToday();
  const [options, setOptions] = useState<PayoutOptions | null>(null);
  const [terms, setTerms] = useState<Record<string, Terms>>({});
  const [consultantId, setConsultantId] = useState("");
  const [from, setFrom] = useState(today.slice(0, 8) + "01");
  const [to, setTo] = useState(today);
  const [preview, setPreview] = useState<PayoutPreview | null>(null);
  const [notes, setNotes] = useState("");
  const [payouts, setPayouts] = useState<Payout[]>([]);
  const [expanded, setExpanded] = useState<Record<string, Payout>>({});
  const [paying, setPaying] = useState<string | null>(null);
  const [pay, setPay] = useState({ mode: "net_banking", reference: "", tds: "", paid_on: today });
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [found, list] = await Promise.all([
        staffApi.payoutOptions(), staffApi.payouts({ from: financialYearStart(today) }),
      ]);
      setOptions(found);
      setTerms(Object.fromEntries(found.consultants.map((c) => [c.id, {
        percent: String(c.payout_share_percent), categories: c.payout_categories,
      }])));
      setPayouts(list);
      if (!consultantId && found.consultants[0]) setConsultantId(found.consultants[0].id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Payouts could not be loaded.");
    }
  }, [today, consultantId]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function run(action: () => Promise<unknown>, after?: () => void) {
    setBusy(true);
    setError(null);
    try {
      await action();
      after?.();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not work.");
    } finally {
      setBusy(false);
    }
  }

  async function loadPreview() {
    setError(null);
    setPreview(null);
    try {
      setPreview(await staffApi.payoutPreview(consultantId, from, to));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The preview could not be prepared.");
    }
  }

  async function toggle(payout: Payout) {
    if (expanded[payout.id]) {
      const next = { ...expanded };
      delete next[payout.id];
      setExpanded(next);
      return;
    }
    setExpanded({ ...expanded, [payout.id]: await staffApi.payout(payout.id) });
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-clay">{error}</p>}

      <Card>
        <CardHeader className="pb-2"><CardTitle>Payout terms</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          {options?.consultants.map((consultant) => {
            const current = terms[consultant.id] ?? { percent: "0", categories: ["consultation"] };
            return (
              <div key={consultant.id} className="flex flex-wrap items-center gap-3 rounded-lg border border-border px-3 py-2">
                <span className="w-48 font-medium">{consultant.full_name}</span>
                <label className="flex items-center gap-1.5">
                  <Input className="w-20" inputMode="numeric" value={current.percent} disabled={!canManage}
                         onChange={(e) => setTerms({ ...terms, [consultant.id]: { ...current, percent: e.target.value.replace(/\D/g, "").slice(0, 3) } })} />
                  % share of
                </label>
                {options.categories.map((category) => (
                  <label key={category} className="flex items-center gap-1">
                    <input type="checkbox" disabled={!canManage} checked={current.categories.includes(category)}
                           onChange={(e) => setTerms({ ...terms, [consultant.id]: { ...current,
                             categories: e.target.checked ? [...current.categories, category] : current.categories.filter((c) => c !== category) } })} />
                    {CATEGORY_LABEL[category] ?? category}
                  </label>
                ))}
                {canManage && (
                  <Button size="sm" variant="outline" disabled={busy}
                          onClick={() => void run(() => staffApi.setPayoutTerms(consultant.id, {
                            share_percent: Number(current.percent || 0), categories: current.categories,
                          }))}>
                    Save
                  </Button>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-2">
          <CardTitle>Prepare a payout</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <select className={SELECT} value={consultantId} onChange={(e) => { setConsultantId(e.target.value); setPreview(null); }}>
              {options?.consultants.map((c) => <option key={c.id} value={c.id}>{c.full_name}</option>)}
            </select>
            <Input type="date" className="w-40" value={from} onChange={(e) => { setFrom(e.target.value); setPreview(null); }} />
            <Input type="date" className="w-40" value={to} max={today} onChange={(e) => { setTo(e.target.value); setPreview(null); }} />
            <Button size="sm" variant="outline" disabled={!consultantId} onClick={() => void loadPreview()}>Preview</Button>
          </div>
        </CardHeader>
        {preview && (
          <CardContent className="space-y-3 text-sm">
            <p>
              {preview.consultant.full_name}: {preview.share_percent}% of{" "}
              {preview.categories.map((c) => CATEGORY_LABEL[c] ?? c).join(", ").toLowerCase()} on fully paid bills.
            </p>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px]">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-ink-faint">
                    <th className="py-1.5">Bill</th><th>Date</th><th>Patient</th>
                    <th className="text-right">Share taken on</th><th className="text-right">Share</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.items.length === 0 && <tr><td colSpan={5} className="py-3 text-ink-muted">No settled bills to pay in this period.</td></tr>}
                  {preview.items.map((item) => (
                    <tr key={`${item.invoice_number}-${item.payment_id ?? "bill"}`} className="border-b border-border last:border-0">
                      <td className="py-1.5">{item.invoice_number}{item.kind === "refund" && <Badge variant="outline" className="ml-2 text-clay">Refund clawback</Badge>}</td>
                      <td>{formatDate(item.invoice_date)}</td>
                      <td>{item.patient_name}</td>
                      <td className="tabular text-right">{formatINR(item.base_paise)}</td>
                      <td className="tabular text-right">{formatINR(item.share_paise)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="font-semibold">
                    <td className="py-1.5" colSpan={3}>Total</td>
                    <td className="tabular text-right">{formatINR(preview.base_paise)}</td>
                    <td className="tabular text-right">{formatINR(preview.share_paise)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
            {preview.waiting.length > 0 && (
              <div className="rounded-lg bg-marigold/10 p-3 text-xs text-marigold-deep">
                <p className="mb-1 font-medium">Waiting for payment — not included</p>
                {preview.waiting.map((bill) => (
                  <p key={bill.invoice_number}>
                    {bill.invoice_number} · {bill.patient_name} · paid {formatINR(bill.paid_paise)} of {formatINR(bill.total_paise)} · {bill.reason}
                  </p>
                ))}
              </div>
            )}
            {canManage && preview.items.length > 0 && (
              <div className="flex flex-wrap gap-2">
                <Input className="min-w-[16rem] flex-1" placeholder="Notes (optional)" value={notes} onChange={(e) => setNotes(e.target.value)} />
                <Button disabled={busy || preview.share_paise <= 0}
                        onClick={() => void run(() => staffApi.approvePayout({ consultant_id: consultantId, date_from: from, date_to: to, notes: notes || null }),
                                                () => { setPreview(null); setNotes(""); })}>
                  {busy && <Loader2 className="h-4 w-4 animate-spin" />} Approve {formatINR(preview.share_paise)}
                </Button>
              </div>
            )}
          </CardContent>
        )}
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle>Payouts this financial year</CardTitle></CardHeader>
        <CardContent className="space-y-2 text-sm">
          {payouts.length === 0 && <p className="text-ink-muted">No payouts yet.</p>}
          {payouts.map((payout) => (
            <div key={payout.id} className="rounded-lg border border-border">
              <div className="flex flex-wrap items-center gap-3 px-3 py-2">
                <button onClick={() => void toggle(payout)} className="text-ink-faint" aria-label="Show bills">
                  {expanded[payout.id] ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </button>
                <span className="font-medium">{payout.payout_number}</span>
                <span>{payout.consultant_name}</span>
                <span className="text-ink-muted">{formatDate(payout.period_from)} – {formatDate(payout.period_to)}</span>
                <span className="tabular">{formatINR(payout.share_paise)}</span>
                <Badge variant="outline" className={payout.status === "cancelled" ? "text-clay" : payout.status === "paid" ? "text-pine" : ""}>
                  {payout.status}
                </Badge>
                {payout.status === "paid" && (
                  <span className="text-xs text-ink-muted">
                    Paid {formatINR(payout.net_paid_paise)}{payout.tds_paise ? ` + TDS ${formatINR(payout.tds_paise)}` : ""} by{" "}
                    {PAY_MODE_LABEL[payout.payment_mode ?? ""] ?? payout.payment_mode} on {formatDate(payout.paid_on)}
                  </span>
                )}
                {canManage && payout.status === "approved" && (
                  <span className="ml-auto flex gap-2">
                    <Button size="sm" onClick={() => { setPaying(payout.id); setCancelling(null); }}>Pay</Button>
                    <Button size="sm" variant="ghost" onClick={() => { setCancelling(payout.id); setPaying(null); }}>Cancel</Button>
                  </span>
                )}
              </div>
              {paying === payout.id && (
                <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2">
                  <select className={SELECT} value={pay.mode} onChange={(e) => setPay({ ...pay, mode: e.target.value })}>
                    {options?.pay_modes.map((mode) => <option key={mode} value={mode}>{PAY_MODE_LABEL[mode] ?? mode}</option>)}
                  </select>
                  {pay.mode !== "cash" && (
                    <Input className="w-44" placeholder="Reference / cheque no." value={pay.reference} onChange={(e) => setPay({ ...pay, reference: e.target.value })} />
                  )}
                  <Input className="w-32" placeholder="TDS ₹" inputMode="decimal" value={pay.tds} onChange={(e) => setPay({ ...pay, tds: e.target.value })} />
                  <Input type="date" className="w-40" value={pay.paid_on} max={today} onChange={(e) => setPay({ ...pay, paid_on: e.target.value })} />
                  <span className="text-ink-muted">Net {formatINR(payout.share_paise - rupeesToPaise(pay.tds || "0"))}</span>
                  <Button size="sm" disabled={busy || (pay.mode !== "cash" && !pay.reference.trim())}
                          onClick={() => void run(() => staffApi.payPayout(payout.id, {
                            mode: pay.mode, reference: pay.reference || null, tds_paise: rupeesToPaise(pay.tds || "0"), paid_on: pay.paid_on,
                          }), () => { setPaying(null); setPay({ mode: "net_banking", reference: "", tds: "", paid_on: today }); setExpanded({}); })}>
                    Record payment
                  </Button>
                </div>
              )}
              {cancelling === payout.id && (
                <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2">
                  <Input className="w-72" placeholder="Reason for cancelling" value={reason} onChange={(e) => setReason(e.target.value)} />
                  <Button size="sm" variant="outline" disabled={busy || reason.trim().length < 3}
                          onClick={() => void run(() => staffApi.cancelPayout(payout.id, reason.trim()), () => { setCancelling(null); setReason(""); setExpanded({}); })}>
                    Cancel payout
                  </Button>
                </div>
              )}
              {expanded[payout.id] && (
                <div className="border-t border-border px-3 py-2 text-xs">
                  <p className="mb-1 text-ink-muted">
                    Approved {formatDateTime(payout.approved_at)} by {payout.approved_by_name}
                    {payout.cancel_reason ? ` · cancelled: ${payout.cancel_reason}` : ""}
                  </p>
                  {expanded[payout.id].items?.map((item) => (
                    <p key={`${item.invoice_number}-${item.payment_id ?? ""}`} className="flex justify-between gap-2">
                      <span>{item.invoice_number} · {item.patient_name}{item.kind === "refund" ? " · refund clawback" : ""}</span>
                      <span className="tabular">{formatINR(item.base_paise)} → {formatINR(item.share_paise)}</span>
                    </p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
