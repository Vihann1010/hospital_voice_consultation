"use client";

/**
 * One claim: where it stands, the next step, the payer's share on the bill,
 * and what the payer has paid.
 *
 * The desk moves the claim and puts the approved amount on the bill. Recording
 * the payer's money is accounts work, behind the finance PIN. Anything that
 * does not add up is shown as the server reports it, never smoothed over.
 */
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Loader2, X } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { ClaimDetail, ClaimStatus } from "@/lib/types/insurance";
import { CLAIM_STATUS_LABEL, SETTLEMENT_MODE_LABEL, statusClass } from "@/lib/types/insurance";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import { formatDate, formatDateTime, hospitalToday } from "@/lib/format";
import { FinanceGate } from "@/components/accounts/finance-gate";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ReasonDialog, type ReasonRequest } from "@/components/ui/reason-dialog";

const SELECT = "h-9 rounded-md border border-border bg-white px-2 text-sm text-ink";
const rupees = (paise: number) => (paise ? String(paise / 100) : "");

const MOVE_AMOUNT: Partial<Record<ClaimStatus, { key: string; label: string; from: (c: ClaimDetail) => number }>> = {
  pre_auth_requested: { key: "pre_auth_requested_paise", label: "Amount asked for (Rs)", from: (c) => c.pre_auth_requested_paise },
  pre_auth_approved: {
    key: "pre_auth_approved_paise", label: "Amount pre-authorised (Rs)",
    from: (c) => c.pre_auth_approved_paise || c.pre_auth_requested_paise,
  },
  submitted: {
    key: "claimed_paise", label: "Amount claimed (Rs)", from: (c) => c.claimed_paise || c.invoice?.total_paise || 0,
  },
  partially_approved: { key: "approved_paise", label: "Amount approved (Rs)", from: (c) => c.approved_paise },
};
const MOVE_TEXT: Partial<Record<ClaimStatus, string>> = {
  rejected: "The payer's reason for rejecting",
  pre_auth_rejected: "The payer's reason for rejecting",
  queried: "What the payer asked for",
};

const EMPTY_SETTLE = {
  received_on: hospitalToday(), received: "", tds: "", deduction: "", deduction_reason: "", mode: "net_banking",
  reference: "", notes: "",
};

function message(err: unknown, fallback: string) {
  return err instanceof Error ? err.message : fallback;
}

function Figure({ label, value, hint, strong }: { label: string; value: string; hint?: string | null; strong?: boolean }) {
  return (
    <div>
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd className={strong ? "font-semibold text-ink" : "text-ink"}>{value}</dd>
      {hint && <dd className="text-[11px] text-ink-faint">{hint}</dd>}
    </div>
  );
}

export function ClaimDetailPanel({
  claimId, canSettle, onChanged, onClose,
}: { claimId: string; canSettle: boolean; onChanged: () => void; onClose: () => void }) {
  const [claim, setClaim] = useState<ClaimDetail | null>(null);
  const [move, setMove] = useState({ status: "" as ClaimStatus | "", amount: "", reference: "", text: "", note: "" });
  const [bookAmount, setBookAmount] = useState("");
  const [settle, setSettle] = useState(EMPTY_SETTLE);
  const [reasonRequest, setReasonRequest] = useState<ReasonRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const accept = useCallback((found: ClaimDetail) => {
    setClaim(found);
    setMove({ status: "", amount: "", reference: "", text: "", note: "" });
    const balance = found.invoice ? found.invoice.balance_paise : found.approved_paise;
    setBookAmount(rupees(Math.min(found.approved_paise, balance)));
  }, []);

  useEffect(() => {
    let live = true;
    setClaim(null);
    setError(null);
    staffApi.claim(claimId)
      .then((found) => live && accept(found))
      .catch((err) => live && setError(message(err, "The claim could not be loaded.")));
    return () => { live = false; };
  }, [claimId, accept]);

  async function run(action: () => Promise<ClaimDetail>, after?: () => void) {
    setBusy(true);
    setError(null);
    try {
      accept(await action());
      after?.();
      onChanged();
    } catch (err) {
      setError(message(err, "That did not go through."));
    } finally {
      setBusy(false);
    }
  }

  if (!claim) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-ink-muted">
          {error ? <span className="text-clay">{error}</span> : <Loader2 className="h-4 w-4 animate-spin" />}
        </CardContent>
      </Card>
    );
  }

  const amountSpec = move.status ? MOVE_AMOUNT[move.status] : undefined;
  const textLabel = move.status ? MOVE_TEXT[move.status] : undefined;

  function submitMove() {
    if (!claim || !move.status) return;
    const body: Record<string, unknown> = { status: move.status, note: move.note.trim() || null };
    if (amountSpec) body[amountSpec.key] = rupeesToPaise(move.amount);
    if (move.status === "approved") body.approved_paise = claim.claimed_paise;
    if (move.status === "submitted" && move.reference.trim()) body.external_reference = move.reference.trim();
    if (move.status === "queried") body.query = move.text;
    if (move.status === "rejected" || move.status === "pre_auth_rejected") body.reason = move.text;
    void run(() => staffApi.moveClaim(claim.id, body));
  }

  function submitSettlement() {
    if (!claim) return;
    void run(() => staffApi.recordSettlement(claim.id, {
      received_on: settle.received_on, received_paise: rupeesToPaise(settle.received), tds_paise: rupeesToPaise(settle.tds),
      deduction_paise: rupeesToPaise(settle.deduction), deduction_reason: settle.deduction_reason.trim() || null,
      mode: settle.mode, reference: settle.reference.trim() || null, notes: settle.notes.trim() || null,
    }), () => setSettle(EMPTY_SETTLE));
  }

  const settlementTotal = rupeesToPaise(settle.received) + rupeesToPaise(settle.tds) + rupeesToPaise(settle.deduction);

  const settlementList = (
    <div className="space-y-2">
      {claim.settlements.length === 0 ? (
        <p className="text-sm text-ink-muted">Nothing recorded from the payer yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead className="text-left text-xs text-ink-muted">
              <tr>
                <th className="py-1.5 pr-2">Date</th>
                <th className="py-1.5 pr-2 text-right">Received</th>
                <th className="py-1.5 pr-2 text-right">TDS</th>
                <th className="py-1.5 pr-2 text-right">Disallowed</th>
                <th className="py-1.5 pr-2">How</th>
                <th className="py-1.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {claim.settlements.map((s) => (
                <tr key={s.id} className={s.cancelled_at ? "text-ink-faint line-through" : ""}>
                  <td className="py-1.5 pr-2">{formatDate(s.received_on)}</td>
                  <td className="py-1.5 pr-2 text-right">{formatINR(s.received_paise)}</td>
                  <td className="py-1.5 pr-2 text-right">{formatINR(s.tds_paise)}</td>
                  <td className="py-1.5 pr-2 text-right" title={s.deduction_reason ?? undefined}>{formatINR(s.deduction_paise)}</td>
                  <td className="py-1.5 pr-2 text-xs">
                    {SETTLEMENT_MODE_LABEL[s.mode] ?? s.mode}{s.reference ? ` ${s.reference}` : ""}
                    <span className="block text-ink-faint">by {s.created_by_name}</span>
                  </td>
                  <td className="py-1.5 text-right text-xs">
                    {s.cancelled_at ? (
                      <span className="no-underline" title={s.cancel_reason ?? undefined}>Cancelled</span>
                    ) : canSettle && (
                      <button className="text-clay hover:underline" onClick={() => setReasonRequest({
                        title: "Cancel this settlement?", destructive: true, confirmLabel: "Cancel settlement",
                        detail: "The books reverse it, and the payer owes this amount again.",
                        run: async (reason) => accept(await staffApi.cancelSettlement(s.id, reason)),
                      })}>Cancel</button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  const settlementForm = canSettle && claim.booked_paise > 0 && claim.outstanding_paise > 0 && (
    <div className="space-y-2 rounded-lg border border-border p-3">
      <p className="text-xs font-medium text-ink">Record what the payer sent — {formatINR(claim.outstanding_paise)} still owed</p>
      <div className="grid gap-2 sm:grid-cols-3">
        <label className="space-y-1"><span className="text-xs text-ink-muted">Date received</span>
          <Input type="date" max={hospitalToday()} value={settle.received_on}
                 onChange={(e) => setSettle({ ...settle, received_on: e.target.value })} /></label>
        <label className="space-y-1"><span className="text-xs text-ink-muted">Received (Rs)</span>
          <Input inputMode="decimal" value={settle.received} onChange={(e) => setSettle({ ...settle, received: e.target.value })} /></label>
        <label className="space-y-1"><span className="text-xs text-ink-muted">TDS deducted (Rs)</span>
          <Input inputMode="decimal" value={settle.tds} onChange={(e) => setSettle({ ...settle, tds: e.target.value })} /></label>
        <label className="space-y-1"><span className="text-xs text-ink-muted">Disallowed (Rs)</span>
          <Input inputMode="decimal" value={settle.deduction} onChange={(e) => setSettle({ ...settle, deduction: e.target.value })} /></label>
        <label className="space-y-1 sm:col-span-2"><span className="text-xs text-ink-muted">Why disallowed</span>
          <Input value={settle.deduction_reason} disabled={!rupeesToPaise(settle.deduction)}
                 onChange={(e) => setSettle({ ...settle, deduction_reason: e.target.value })} /></label>
        <label className="space-y-1"><span className="text-xs text-ink-muted">Paid by</span>
          <select className={`${SELECT} w-full`} value={settle.mode} onChange={(e) => setSettle({ ...settle, mode: e.target.value })}>
            {Object.entries(SETTLEMENT_MODE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
        <label className="space-y-1 sm:col-span-2"><span className="text-xs text-ink-muted">UTR, cheque or UPI reference</span>
          <Input value={settle.reference} onChange={(e) => setSettle({ ...settle, reference: e.target.value })} /></label>
      </div>
      <p className="text-xs text-ink-muted">
        Accounts for {formatINR(settlementTotal)} of {formatINR(claim.outstanding_paise)}.
        {settlementTotal === claim.outstanding_paise && settlementTotal > 0 && " This settles the claim."}
      </p>
      <Button size="sm" disabled={busy || settlementTotal <= 0 || settlementTotal > claim.outstanding_paise}
              onClick={submitSettlement}>
        {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Record settlement
      </Button>
    </div>
  );

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 pb-2">
        <div>
          <CardTitle className="font-mono text-base">{claim.claim_number}</CardTitle>
          <p className={`text-sm font-medium ${statusClass(claim.status)}`}>{claim.status_label}</p>
          <p className="text-sm text-ink">
            {claim.patient.name}{claim.patient.uhid ? ` · ${claim.patient.uhid}` : ""}
          </p>
          <p className="text-xs text-ink-muted">
            {claim.payer_name} · Policy {claim.policy.policy_number}
            {claim.policy.member_id ? ` · Member ${claim.policy.member_id}` : ""}
            {claim.external_reference ? ` · Payer's ref ${claim.external_reference}` : ""}
          </p>
          <p className="text-xs text-ink-muted">
            {[claim.admission && `Admission ${claim.admission.ip_number}`, claim.invoice && `Bill ${claim.invoice.invoice_number}`]
              .filter(Boolean).join(" · ") || "No admission or bill linked"}
          </p>
        </div>
        <Button size="sm" variant="ghost" aria-label="Close claim" onClick={onClose}><X className="h-4 w-4" /></Button>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {error && <p className="text-sm text-clay">{error}</p>}
        {claim.attention.map((line) => (
          <p key={line} className="flex items-start gap-2 rounded-lg border border-clay/30 bg-clay/5 p-2 text-xs text-clay">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {line}
          </p>
        ))}

        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Figure label="Pre-auth asked" value={formatINR(claim.pre_auth_requested_paise)} />
          <Figure label="Pre-authorised" value={formatINR(claim.pre_auth_approved_paise)} />
          <Figure label="Claimed" value={formatINR(claim.claimed_paise)} />
          <Figure label="Approved" value={formatINR(claim.approved_paise)} />
          <Figure label="On the bill" value={formatINR(claim.booked_paise)}
                  hint={claim.booked_on ? `since ${formatDate(claim.booked_on)} · ${claim.booking_receipt_number}` : null} />
          <Figure label="Received" value={formatINR(claim.received_paise)} hint={claim.tds_paise ? `TDS ${formatINR(claim.tds_paise)}` : null} />
          <Figure label="Disallowed" value={formatINR(claim.deducted_paise)} />
          <Figure label="Payer owes" value={formatINR(claim.outstanding_paise)} strong />
        </dl>
        {claim.invoice && (
          <p className="text-xs text-ink-muted">
            Bill {claim.invoice.invoice_number}: total {formatINR(claim.invoice.total_paise)}, family still owes{" "}
            <span className="font-medium text-ink">{formatINR(claim.invoice.balance_paise)}</span>.
          </p>
        )}
        {claim.query_detail && claim.status === "queried" && (
          <p className="text-xs text-clay">Payer asked: {claim.query_detail}</p>
        )}
        {claim.rejection_reason && (claim.status === "rejected" || claim.status === "pre_auth_rejected") && (
          <p className="text-xs text-clay">Rejected: {claim.rejection_reason}</p>
        )}

        {claim.next_statuses.length > 0 && (
          <div className="space-y-2 rounded-lg border border-border p-3">
            <p className="text-xs font-medium text-ink">Next step</p>
            <div className="flex flex-wrap items-end gap-2">
              <select className={SELECT} value={move.status} onChange={(e) => {
                const status = e.target.value as ClaimStatus | "";
                const spec = status ? MOVE_AMOUNT[status] : undefined;
                setMove({ ...move, status, amount: spec ? rupees(spec.from(claim)) : "", text: "" });
              }}>
                <option value="">Choose…</option>
                {claim.next_statuses.map((s) => <option key={s} value={s}>{CLAIM_STATUS_LABEL[s]}</option>)}
              </select>
              {amountSpec && (
                <label className="space-y-1"><span className="text-xs text-ink-muted">{amountSpec.label}</span>
                  <Input className="w-36" inputMode="decimal" value={move.amount}
                         onChange={(e) => setMove({ ...move, amount: e.target.value })} /></label>
              )}
              {move.status === "submitted" && (
                <label className="space-y-1"><span className="text-xs text-ink-muted">Payer&apos;s claim reference</span>
                  <Input className="w-44" value={move.reference || claim.external_reference || ""}
                         onChange={(e) => setMove({ ...move, reference: e.target.value })} /></label>
              )}
              {move.status === "approved" && (
                <span className="text-xs text-ink-muted">Approves the full {formatINR(claim.claimed_paise)} claimed.</span>
              )}
            </div>
            {textLabel && (
              <Input placeholder={textLabel} value={move.text} onChange={(e) => setMove({ ...move, text: e.target.value })} />
            )}
            {move.status && (
              <div className="flex flex-wrap gap-2">
                <Input className="min-w-0 flex-1" placeholder="Note (optional)" value={move.note}
                       onChange={(e) => setMove({ ...move, note: e.target.value })} />
                <Button size="sm" disabled={busy} onClick={submitMove}>
                  {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
                </Button>
              </div>
            )}
          </div>
        )}

        {(claim.can_book || claim.booked_paise > 0) && (
          <div className="space-y-2 rounded-lg border border-border p-3">
            <p className="text-xs font-medium text-ink">The payer&apos;s share on the bill</p>
            {claim.can_book ? (
              <div className="flex flex-wrap items-end gap-2">
                <label className="space-y-1"><span className="text-xs text-ink-muted">Amount (Rs)</span>
                  <Input className="w-36" inputMode="decimal" value={bookAmount} onChange={(e) => setBookAmount(e.target.value)} /></label>
                <Button size="sm" disabled={busy || rupeesToPaise(bookAmount) <= 0}
                        onClick={() => void run(() => staffApi.bookClaim(claim.id, rupeesToPaise(bookAmount)))}>
                  Put on {claim.invoice ? `bill ${claim.invoice.invoice_number}` : "the final bill"}
                </Button>
                <span className="text-xs text-ink-muted">The family is then asked only for the rest.</span>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <span>{formatINR(claim.booked_paise)} is on the bill.</span>
                <Button size="sm" variant="ghost" className="text-clay" onClick={() => setReasonRequest({
                  title: "Take the payer's share off the bill?", destructive: true, confirmLabel: "Take it off",
                  detail: "The insurance entry on the bill is struck, and the family owes that amount again until it is put back.",
                  run: async (reason) => accept(await staffApi.unbookClaim(claim.id, reason)),
                })}>Take off the bill</Button>
              </div>
            )}
          </div>
        )}

        {(claim.booked_paise > 0 || claim.settlements.length > 0) && (
          <div className="space-y-2">
            <p className="text-xs font-medium text-ink">What the payer sent</p>
            {canSettle ? (
              <FinanceGate>
                <div className="space-y-3">{settlementList}{settlementForm}</div>
              </FinanceGate>
            ) : settlementList}
          </div>
        )}

        <div className="space-y-1">
          <p className="text-xs font-medium text-ink">History</p>
          <ol className="space-y-1.5 border-l border-border pl-3">
            {claim.history.map((entry, index) => (
              <li key={`${entry.at}-${index}`} className="text-xs">
                <span className="text-ink-faint">{formatDateTime(entry.at)}</span>{" "}
                <span className="font-medium text-ink">{CLAIM_STATUS_LABEL[entry.status] ?? entry.status}</span>{" "}
                <span className="text-ink-muted">by {entry.by}</span>
                {entry.note && <span className="block text-ink-muted">{entry.note}</span>}
              </li>
            ))}
          </ol>
        </div>
      </CardContent>
      <ReasonDialog request={reasonRequest} onClose={() => setReasonRequest(null)} onDone={onChanged} />
    </Card>
  );
}
