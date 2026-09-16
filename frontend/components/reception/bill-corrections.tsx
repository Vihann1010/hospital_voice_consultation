"use client";

/**
 * Finding a past bill, and undoing it.
 *
 * Corrections are rare and consequential, which is the opposite of the
 * counter's usual work, so this screen is deliberately slower: every
 * destructive action asks for a written reason, and each one names what it
 * will do before doing it.
 *
 * The order is enforced by the API, not here — a receipt before its bill, a
 * bill before its registration. What this screen does is make the order
 * visible, so a clerk meets an explanation rather than a refusal.
 */
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Banknote,
  FilePenLine,
  Loader2,
  Trash2,
  Lock,
  Printer,
  RotateCcw,
  Search,
  Undo2,
  X,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { getToken } from "@/lib/auth";
import type { Invoice, InvoiceStatus, InvoiceSummary } from "@/lib/types/emr";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import { formatDateTime } from "@/lib/format";
import { useToast } from "@/components/ui/toast";
import { ReasonDialog, type ReasonRequest } from "@/components/ui/reason-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const STATUS_STYLE: Record<InvoiceStatus, string> = {
  draft: "bg-mint-card text-ink-faint",
  issued: "bg-mint text-pine",
  paid: "bg-marigold/15 text-marigold-deep",
  partially_paid: "bg-marigold/10 text-marigold-deep",
  cancelled: "bg-clay/10 text-clay",
  refunded: "bg-clay/10 text-clay",
};

async function printPdf(url: string) {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!response.ok) throw new Error("That document is not available.");
  const blobUrl = URL.createObjectURL(await response.blob());
  window.open(blobUrl, "_blank");
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
}

/** Money actually going back to the patient. Distinct from cancelling a
 *  receipt, which says the entry was a mistake and no money moved. */
function RefundForm({
  invoice,
  onDone,
  onCancel,
}: {
  invoice: Invoice;
  onDone: (label: string) => void;
  onCancel: () => void;
}) {
  const collected = invoice.paid_paise;
  const [amount, setAmount] = useState(String(collected / 100));
  const [destination, setDestination] = useState("cash");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const paise = rupeesToPaise(amount);
  const problem =
    paise <= 0
      ? "Enter how much is going back."
      : paise > collected
        ? `Only ${formatINR(collected)} was collected on this bill.`
        : reason.trim().length < 3
          ? "Give a reason — it is recorded against your name."
          : null;

  async function submit() {
    if (problem) return;
    setBusy(true);
    setError(null);
    try {
      await staffApi.refundInvoice(invoice.id, {
        amount_paise: paise,
        reason: reason.trim(),
        mode: destination === "wallet" ? "cash" : destination,
        to_wallet: destination === "wallet",
      });
      onDone(
        destination === "wallet"
          ? "Refunded to the patient's credit"
          : "Refund recorded"
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "The refund did not go through.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 border-t border-border bg-mint-card px-4 py-3">
      <p className="text-[11px] text-ink-muted">
        Returns money to the patient. {formatINR(collected)} was collected on this bill.
      </p>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-ink-faint">
          Amount (Rs)
          <Input
            className="mt-0.5 h-8 w-28 text-sm"
            inputMode="decimal"
            value={amount}
            autoFocus
            onChange={(event) => setAmount(event.target.value)}
          />
        </label>
        <label className="text-[11px] text-ink-faint">
          Given back as
          <select
            className="mt-0.5 block h-8 rounded-md border border-border bg-white px-2 text-sm text-ink"
            value={destination}
            onChange={(event) => setDestination(event.target.value)}
          >
            <option value="cash">Cash from the drawer</option>
            <option value="upi">UPI</option>
            <option value="net_banking">Bank transfer</option>
            <option value="card">Card reversal</option>
            <option value="cheque">Cheque</option>
            <option value="wallet">Keep as credit for the patient</option>
          </select>
        </label>
      </div>
      <Input
        className="h-8 text-sm"
        value={reason}
        placeholder="Reason, e.g. test billed but not done"
        onChange={(event) => setReason(event.target.value)}
      />
      {(error || problem) && (
        <p className="text-[11px] text-clay">{error ?? problem}</p>
      )}
      <div className="flex gap-2">
        <Button size="sm" className="h-7 text-xs" disabled={busy || Boolean(problem)} onClick={() => void submit()}>
          {busy && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
          Refund {formatINR(paise > 0 ? paise : 0)}
        </Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={onCancel}>
          Keep as it is
        </Button>
      </div>
    </div>
  );
}

/** Correcting what a bill charges for, before anybody has paid it.
 *  The lines are sent whole: the bill becomes exactly what is listed here. */
function AmendForm({
  invoice,
  onDone,
  onCancel,
}: {
  invoice: Invoice;
  onDone: (label: string) => void;
  onCancel: () => void;
}) {
  interface Line {
    description: string;
    quantity: string;
    rate: string;
    discount: string;
    remark: string;
  }
  // A stored line carries its own discount plus its share of any bill-wide
  // discount, which is not separated in the ledger. Both are therefore shown
  // against the line and the bill-wide box starts empty: the net is identical,
  // and the clerk can see which charge the money came off.
  const [lines, setLines] = useState<Line[]>(
    (invoice.lines ?? []).map((line) => ({
      description: line.description,
      quantity: String(line.quantity),
      rate: String(line.unit_rate_paise / 100),
      discount: line.discount_paise ? String(line.discount_paise / 100) : "",
      remark: line.remark ?? "",
    }))
  );
  const [discount, setDiscount] = useState("0");
  const [discountReason, setDiscountReason] = useState(invoice.discount_reason ?? "");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lineGross = (line: Line) =>
    rupeesToPaise(line.rate) * (Number(line.quantity) || 0);
  const gross = lines.reduce((sum, line) => sum + lineGross(line), 0);
  const lineDiscounts = lines.reduce(
    (sum, line) => sum + rupeesToPaise(line.discount || "0"),
    0
  );
  const net = gross - lineDiscounts - rupeesToPaise(discount);
  const problem =
    lines.length === 0
      ? "A bill needs at least one line."
      : lines.some((line) => !line.description.trim() || rupeesToPaise(line.rate) < 0)
        ? "Every line needs a description and a rate."
        : lines.some((line) => rupeesToPaise(line.discount || "0") > lineGross(line))
          ? "A discount cannot be larger than the charge it comes off."
          : net < 0
          ? "The discount is more than the bill."
          : rupeesToPaise(discount) > 0 && !discountReason.trim()
            ? "A discount needs a reason."
            : reason.trim().length < 3
              ? "Say why the bill is being corrected."
              : null;

  const setLine = (index: number, patch: Partial<Line>) =>
    setLines(lines.map((line, at) => (at === index ? { ...line, ...patch } : line)));

  async function submit() {
    if (problem) return;
    setBusy(true);
    setError(null);
    try {
      await staffApi.amendInvoice(invoice.id, {
        items: lines.map((line) => ({
          description: line.description.trim(),
          quantity: Number(line.quantity) || 1,
          unit_rate_paise: rupeesToPaise(line.rate),
          discount_paise: rupeesToPaise(line.discount || "0"),
          remark: line.remark.trim() || null,
        })),
        invoice_discount_paise: rupeesToPaise(discount),
        discount_reason: discountReason.trim() || null,
        reason: reason.trim(),
      });
      onDone("Bill corrected");
    } catch (err) {
      setError(err instanceof Error ? err.message : "The bill could not be corrected.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 border-t border-border bg-mint-card px-4 py-3">
      <p className="text-[11px] text-ink-muted">
        The bill becomes exactly these lines. Its number and date do not change, and the correction
        is recorded on it.
      </p>
      <ul className="space-y-1.5">
        {lines.map((line, index) => (
          <li key={index} className="space-y-1">
            <div className="flex items-center gap-1.5">
              <Input
                className="h-8 min-w-0 flex-1 text-xs"
                value={line.description}
                placeholder="What is being charged for"
                onChange={(event) => setLine(index, { description: event.target.value })}
              />
              <Input
                className="h-8 w-14 text-xs"
                inputMode="numeric"
                value={line.quantity}
                aria-label="Quantity"
                onChange={(event) => setLine(index, { quantity: event.target.value })}
              />
              <Input
                className="h-8 w-24 text-right text-xs"
                inputMode="decimal"
                value={line.rate}
                aria-label="Rate in rupees"
                onChange={(event) => setLine(index, { rate: event.target.value })}
              />
              <button
                type="button"
                aria-label="Remove this line"
                className="rounded p-1 text-ink-faint hover:text-clay"
                onClick={() => setLines(lines.filter((_, at) => at !== index))}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
            <div className="flex items-center gap-1.5 pr-6">
              <Input
                className="h-7 w-24 text-right text-xs"
                inputMode="decimal"
                value={line.discount}
                placeholder="Disc (Rs)"
                aria-label="Discount on this line in rupees"
                onChange={(event) => setLine(index, { discount: event.target.value })}
              />
              <Input
                className="h-7 min-w-0 flex-1 text-xs"
                value={line.remark}
                maxLength={255}
                placeholder="Remark for this charge"
                aria-label="Remark for this charge"
                onChange={(event) => setLine(index, { remark: event.target.value })}
              />
            </div>
          </li>
        ))}
      </ul>
      <Button
        size="sm"
        variant="ghost"
        className="h-7 text-xs"
        onClick={() =>
          setLines([
            ...lines,
            { description: "", quantity: "1", rate: "", discount: "", remark: "" },
          ])
        }
      >
        Add a line
      </Button>
      <div className="flex flex-wrap items-end gap-2">
        <label className="text-[11px] text-ink-faint">
          Discount on the whole bill (Rs)
          <Input
            className="mt-0.5 h-8 w-24 text-sm"
            inputMode="decimal"
            value={discount}
            onChange={(event) => setDiscount(event.target.value)}
          />
        </label>
        <label className="min-w-0 flex-1 text-[11px] text-ink-faint">
          Discount approved because
          <Input
            className="mt-0.5 h-8 text-sm"
            value={discountReason}
            disabled={rupeesToPaise(discount) === 0}
            onChange={(event) => setDiscountReason(event.target.value)}
          />
        </label>
      </div>
      <Input
        className="h-8 text-sm"
        value={reason}
        placeholder="Why the bill is being corrected"
        onChange={(event) => setReason(event.target.value)}
      />
      <p className="text-[11px] text-ink-muted">
        New total {formatINR(net > 0 ? net : 0)}, was {formatINR(invoice.total_paise)}.
      </p>
      {(error || problem) && <p className="text-[11px] text-clay">{error ?? problem}</p>}
      <div className="flex gap-2">
        <Button size="sm" className="h-7 text-xs" disabled={busy || Boolean(problem)} onClick={() => void submit()}>
          {busy && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
          Correct the bill
        </Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={onCancel}>
          Keep as it is
        </Button>
      </div>
    </div>
  );
}

function BillDetail({
  invoiceId,
  canCorrect,
  onChanged,
  onClose,
}: {
  invoiceId: string;
  canCorrect: boolean;
  onChanged: () => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [ask, setAsk] = useState<ReasonRequest | null>(null);
  const [refunding, setRefunding] = useState(false);
  const [amending, setAmending] = useState(false);

  const load = useCallback(async () => {
    try {
      setInvoice(await staffApi.invoice(invoiceId));
    } catch {
      setInvoice(null);
    }
  }, [invoiceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const done = useCallback(
    (label: string) => {
      void load();
      onChanged();
      toast.success(label);
    },
    [load, onChanged, toast]
  );

  if (!invoice) {
    return (
      <div className="rounded-xl border border-pine/10 bg-white p-4 text-xs text-ink-faint">
        Loading the bill…
      </div>
    );
  }

  const cancelled = invoice.status === "cancelled";
  const livePayments = (invoice.payments ?? []).filter((p) => !p.cancelled_at);

  return (
    <div className="rounded-xl border border-pine/10 bg-white">
      <header className="flex items-center gap-2 border-b border-pine/10 px-4 py-3">
        <div className="min-w-0">
          <p className="font-display text-sm font-semibold text-pine">
            {invoice.invoice_number}
          </p>
          <p className="text-[11px] text-ink-faint">
            {formatDateTime(invoice.issued_at ?? invoice.created_at)} ·{" "}
            {invoice.created_by_name || "—"}
          </p>
        </div>
        <span
          className={cn(
            "ml-auto rounded px-2 py-0.5 text-[11px] font-medium capitalize",
            STATUS_STYLE[invoice.status]
          )}
        >
          {invoice.status.replace("_", " ")}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-ink-faint hover:text-clay"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      {invoice.payout_locked_at && (
        <p className="flex items-start gap-1.5 border-b border-border bg-mint-card px-4 py-2 text-[11px] text-ink-muted">
          <Lock className="mt-0.5 h-3 w-3 shrink-0" />
          Counted into a settled consultant payout. Nothing on this bill can be
          changed — a credit note is the only remedy.
        </p>
      )}

      {invoice.amendment_count > 0 && (
        <p className="border-b border-border bg-mint-card px-4 py-2 text-[11px] text-ink-muted">
          Corrected {invoice.amendment_count}{" "}
          {invoice.amendment_count === 1 ? "time" : "times"}
          {invoice.amendment_reason ? ` — ${invoice.amendment_reason}` : ""}
        </p>
      )}

      {cancelled && invoice.cancellation_reason && (
        <p className="border-b border-clay/20 bg-clay/5 px-4 py-2 text-[11px] text-clay">
          Cancelled: {invoice.cancellation_reason}
        </p>
      )}

      <ul className="divide-y divide-border">
        {(invoice.lines ?? []).map((line) => (
          <li key={line.id} className="flex items-center gap-2 px-4 py-1.5 text-xs">
            <span className="min-w-0 flex-1 truncate text-ink">{line.description}</span>
            <span className="tabular text-ink-faint">×{line.quantity}</span>
            <span className="tabular w-20 text-right text-ink">
              {formatINR(line.total_paise)}
            </span>
          </li>
        ))}
      </ul>

      <div className="flex items-center gap-2 border-t border-border px-4 py-2 text-sm">
        <span className="text-ink-muted">Total</span>
        <span className="tabular ml-auto font-semibold text-pine">
          {formatINR(invoice.total_paise)}
        </span>
        {invoice.total_paise !== invoice.paid_paise && (
          <span className="tabular text-[11px] text-clay">
            balance {formatINR(invoice.total_paise - invoice.paid_paise)}
          </span>
        )}
      </div>

      {(invoice.payments ?? []).length > 0 && (
        <ul className="divide-y divide-border border-t border-border">
          {(invoice.payments ?? []).map((payment) => (
            <li
              key={payment.id}
              className={cn(
                "flex items-center gap-2 px-4 py-2 text-xs",
                payment.cancelled_at && "opacity-50"
              )}
            >
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    "truncate text-ink",
                    payment.cancelled_at && "line-through"
                  )}
                >
                  {payment.receipt_number} · {payment.mode.replace("_", " ")}
                  {payment.is_refund ? " · refund" : ""}
                </p>
                <p className="truncate text-[10px] text-ink-faint">
                  {formatDateTime(payment.received_at)}
                  {payment.cancelled_at
                    ? ` · cancelled: ${payment.cancellation_reason ?? ""}`
                    : ""}
                </p>
              </div>
              <span className="tabular shrink-0 text-ink">
                {formatINR(payment.amount_paise)}
              </span>
              <button
                type="button"
                onClick={() => void printPdf(staffApi.receiptPdfUrl(payment.id))}
                className="shrink-0 rounded p-1 text-ink-faint hover:text-pine"
                aria-label="Print this receipt"
              >
                <Printer className="h-3 w-3" />
              </button>
              {canCorrect && !payment.cancelled_at && (
                <button
                  type="button"
                  onClick={() =>
                    setAsk({
                      title: `Cancel receipt ${payment.receipt_number}?`,
                      detail:
                        "This records that the entry was a mistake and no money moved. " +
                        "If money did go back to the patient, issue a refund instead.",
                      confirmLabel: "Cancel receipt",
                      destructive: true,
                      run: (reason) => staffApi.cancelReceipt(payment.id, reason),
                    })
                  }
                  className="shrink-0 rounded p-1 text-ink-faint hover:text-clay"
                  aria-label="Cancel this receipt"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <ReasonDialog
        request={ask}
        onClose={() => setAsk(null)}
        onDone={() => done("Done")}
      />

      {amending && (
        <AmendForm
          invoice={invoice}
          onCancel={() => setAmending(false)}
          onDone={(label) => {
            setAmending(false);
            done(label);
          }}
        />
      )}

      {refunding && (
        <RefundForm
          invoice={invoice}
          onCancel={() => setRefunding(false)}
          onDone={(label) => {
            setRefunding(false);
            done(label);
          }}
        />
      )}

      <div className="flex flex-wrap gap-1.5 border-t border-border px-4 py-2.5">
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs"
          onClick={() =>
            void printPdf(`${staffApi.invoicePdfUrl(invoice.id)}?duplicate=true`)
          }
        >
          <Printer className="mr-1 h-3 w-3" />
          Reprint (duplicate)
        </Button>

        {canCorrect && !cancelled && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs text-clay hover:text-clay"
            onClick={() =>
              setAsk({
                title: `Cancel bill ${invoice.invoice_number}?`,
                detail:
                  "The number is kept and shown as cancelled — it is never reused, " +
                  "because an auditor checks the sequence.",
                confirmLabel: "Cancel bill",
                destructive: true,
                run: (reason) => staffApi.cancelInvoice(invoice.id, reason),
              })
            }
          >
            <X className="mr-1 h-3 w-3" />
            Cancel bill
          </Button>
        )}

        {canCorrect && !cancelled && invoice.paid_paise === 0 && !invoice.payout_locked_at && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => setAmending((open) => !open)}
          >
            <FilePenLine className="mr-1 h-3 w-3" />
            Correct bill
          </Button>
        )}

        {canCorrect && !cancelled && invoice.paid_paise > 0 && !invoice.payout_locked_at && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() => setRefunding((open) => !open)}
          >
            <Banknote className="mr-1 h-3 w-3" />
            Refund
          </Button>
        )}

        {canCorrect && cancelled && (
          <Button
            size="sm"
            variant="outline"
            className="h-7 text-xs"
            onClick={() =>
              setAsk({
                title: `Reinstate bill ${invoice.invoice_number}?`,
                detail: "Its registration has to be live first.",
                confirmLabel: "Reinstate bill",
                run: (reason) => staffApi.uncancelInvoice(invoice.id, reason),
              })
            }
          >
            <Undo2 className="mr-1 h-3 w-3" />
            Reinstate bill
          </Button>
        )}

        {canCorrect && invoice.visit_id && !cancelled && livePayments.length === 0 && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs text-ink-faint"
            onClick={() =>
              setAsk({
                title: "Cancel the registration too?",
                detail:
                  "Every bill against it must already be cancelled. The patient comes " +
                  "off today's queue.",
                confirmLabel: "Cancel registration",
                destructive: true,
                run: (reason) =>
                  staffApi.cancelVisit(invoice.visit_id as string, reason),
              })
            }
          >
            <RotateCcw className="mr-1 h-3 w-3" />
            Cancel registration
          </Button>
        )}
      </div>
    </div>
  );
}

export function BillCorrections({ canCorrect }: { canCorrect: boolean }) {
  const [term, setTerm] = useState("");
  const [items, setItems] = useState<InvoiceSummary[] | null>(null);
  const [total, setTotal] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (q: string) => {
    try {
      const result = await staffApi.invoices({ q: q.trim() || undefined, limit: 40 });
      setItems(result.items);
      setTotal(result.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not search bills.");
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => void load(term), term ? 250 : 0);
    return () => clearTimeout(timer);
  }, [term, load]);

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_420px]">
      <section className="rounded-xl border border-pine/10 bg-white">
        <header className="flex items-center gap-2 border-b border-pine/10 px-4 py-3">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
            <Input
              value={term}
              onChange={(event) => setTerm(event.target.value)}
              placeholder="Bill number, UHID, name or phone"
              className="h-9 pl-8 text-sm"
              autoFocus
            />
          </div>
          {items && (
            <span className="shrink-0 text-[11px] text-ink-faint">
              {items.length} of {total}
            </span>
          )}
        </header>

        {error && <p className="px-4 py-2 text-xs text-clay">{error}</p>}

        {items && items.length === 0 && (
          <p className="px-4 py-8 text-center text-xs text-ink-faint">
            No bills match that.
          </p>
        )}

        <ul className="max-h-[calc(100vh-300px)] overflow-y-auto">
          {(items ?? []).map((bill) => (
            <li key={bill.id}>
              <button
                type="button"
                onClick={() => setOpenId(bill.id)}
                className={cn(
                  "flex w-full items-center gap-2 border-b border-border px-4 py-2 text-left transition hover:bg-mint",
                  openId === bill.id && "bg-mint"
                )}
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-ink">
                    {bill.patient_name}
                    {bill.payout_locked && (
                      <Lock className="ml-1 inline h-2.5 w-2.5 text-ink-faint" />
                    )}
                  </p>
                  <p className="truncate text-[10px] text-ink-faint">
                    {bill.invoice_number} · {bill.uhid ?? "—"} ·{" "}
                    {formatDateTime(bill.issued_at ?? bill.created_at)}
                    {bill.amendment_count > 0 ? ` · corrected ${bill.amendment_count}×` : ""}
                  </p>
                </div>
                <span className="tabular shrink-0 text-xs text-ink">
                  {formatINR(bill.total_paise)}
                </span>
                <span
                  className={cn(
                    "shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium capitalize",
                    STATUS_STYLE[bill.status]
                  )}
                >
                  {bill.status.replace("_", " ")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </section>

      <div>
        {openId ? (
          <BillDetail
            invoiceId={openId}
            canCorrect={canCorrect}
            onChanged={() => void load(term)}
            onClose={() => setOpenId(null)}
          />
        ) : (
          <div className="rounded-xl border border-dashed border-border p-6 text-center">
            <AlertTriangle className="mx-auto h-4 w-4 text-ink-faint" />
            <p className="mt-1.5 text-xs text-ink-muted">
              Pick a bill to reprint or correct it.
            </p>
            {!canCorrect && (
              <p className="mt-1 text-[11px] text-ink-faint">
                Cancelling and reinstating need a supervisor.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
