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
import { formatINR } from "@/lib/types/emr";
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
