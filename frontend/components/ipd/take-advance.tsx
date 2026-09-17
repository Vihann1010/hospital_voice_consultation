"use client";

/**
 * Taking an advance from an inpatient's family.
 *
 * A real collection with a receipt from the same series as every other
 * payment. It is held in the patient's wallet against this stay and settles
 * the final bill, so it is counted in the drawer once, on the day it is taken.
 */
import { useState } from "react";
import { IndianRupee, Loader2 } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { getToken } from "@/lib/auth";
import type { PaymentMode } from "@/lib/types/emr";
import { rupeesToPaise } from "@/lib/types/emr";
import { PaymentModeFields } from "@/components/finance/payment-mode-fields";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

/** How an advance can be paid. Not the wallet itself, and a waiver is not money. */
export const ADVANCE_MODES: { value: PaymentMode; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "upi", label: "UPI" },
  { value: "card", label: "Card" },
  { value: "net_banking", label: "Net banking" },
  { value: "cheque", label: "Cheque" },
];

/** Receipts are behind bearer auth, so fetch then open the PDF blob. */
export async function openWalletReceipt(entryId: string) {
  const response = await fetch(staffApi.walletReceiptPdfUrl(entryId), {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!response.ok) return;
  const url = URL.createObjectURL(await response.blob());
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

export function TakeAdvance({ admissionId, onDone }: { admissionId: string; onDone: () => void }) {
  const [amount, setAmount] = useState("");
  const [mode, setMode] = useState<PaymentMode>("cash");
  const [details, setDetails] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const result = await staffApi.takeAdmissionAdvance(admissionId, {
        amount_paise: rupeesToPaise(amount),
        mode,
        mode_details: Object.keys(details).length ? details : null,
      });
      setDone(result.entry.receipt_number);
      setAmount("");
      setDetails({});
      onDone();
      void openWalletReceipt(result.entry.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The advance could not be taken.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2 rounded-xl border border-border p-3">
      <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">Take advance</p>
      <div className="flex gap-2">
        <Input value={amount} inputMode="decimal" placeholder="Amount ₹"
               onChange={(e) => setAmount(e.target.value)} />
        <select aria-label="Paid by" value={mode} className="field-input w-32"
                onChange={(e) => { setMode(e.target.value as PaymentMode); setDetails({}); }}>
          {ADVANCE_MODES.map((option) => (
            <option key={option.value} value={option.value}>{option.label}</option>
          ))}
        </select>
        <Button onClick={() => void submit()} disabled={busy || !(rupeesToPaise(amount || "0") > 0)}>
          {busy ? <Loader2 className="animate-spin" /> : <IndianRupee />}
        </Button>
      </div>
      <PaymentModeFields mode={mode} values={details} onChange={setDetails} />
      {error && <p className="text-xs text-clay">{error}</p>}
      {done && <p className="text-xs text-pine">Receipt {done} issued.</p>}
    </div>
  );
}
