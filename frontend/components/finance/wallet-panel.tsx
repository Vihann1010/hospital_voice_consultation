"use client";

/**
 * A patient's credit with the hospital.
 *
 * Shown at the counter the moment a patient is selected, because the single
 * most expensive mistake here is taking cash from somebody who already has
 * money on account — the hospital ends up holding two payments and the
 * patient finds out months later.
 *
 * The ledger is shown, not just the balance. "You have ₹500" invites an
 * argument; "₹2,000 deposited on the 3rd, ₹1,500 applied to bill 214" ends
 * one.
 */
import { useCallback, useEffect, useState } from "react";
import { ArrowDownLeft, ArrowUpRight, Loader2, Printer, Wallet as WalletIcon } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { getToken } from "@/lib/auth";
import type { PaymentMode, Wallet, WalletEntry } from "@/lib/types/emr";
import { PAYMENT_MODES, WALLET_KIND_LABEL, formatINR, rupeesToPaise } from "@/lib/types/emr";
import { formatDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PaymentModeFields, cleanModeDetails } from "@/components/finance/payment-mode-fields";
import { cn } from "@/lib/utils";

/** Modes that can fund a deposit. A waiver is money never collected, and a
 *  wallet cannot top itself up. */
const DEPOSIT_MODES = PAYMENT_MODES.filter(
  (option) => option.value !== "waiver" && option.value !== "wallet" &&
    option.value !== "insurance"
);

async function openPdf(url: string) {
  // Fetched with the bearer token rather than opened as a link: the PDF
  // routes are authenticated, and a plain window.open would get a 401.
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!response.ok) return;
  const objectUrl = URL.createObjectURL(await response.blob());
  window.open(objectUrl, "_blank");
  // Revoked late: revoking immediately can race the new tab's own load.
  setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}

function EntryRow({ entry }: { entry: WalletEntry }) {
  const incoming = entry.amount_paise > 0;
  const printable = entry.kind === "deposit" || entry.kind === "withdrawal";
  return (
    <li className="flex items-start gap-2 border-b border-border px-3 py-2 last:border-b-0">
      <span
        className={cn(
          "mt-0.5 shrink-0 rounded-full p-1",
          incoming ? "bg-marigold/15 text-marigold-deep" : "bg-mint text-pine"
        )}
      >
        {incoming ? (
          <ArrowDownLeft className="h-3 w-3" />
        ) : (
          <ArrowUpRight className="h-3 w-3" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-xs font-medium text-ink">{WALLET_KIND_LABEL[entry.kind]}</p>
        <p className="truncate text-[11px] text-ink-faint">
          {formatDateTime(entry.created_at)}
          {entry.reason ? ` · ${entry.reason}` : ""}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p
          className={cn(
            "tabular text-xs font-medium",
            incoming ? "text-marigold-deep" : "text-ink"
          )}
        >
          {incoming ? "+" : "−"}
          {formatINR(Math.abs(entry.amount_paise))}
        </p>
        <p className="tabular text-[10px] text-ink-faint">
          {formatINR(entry.balance_after_paise)}
        </p>
      </div>
      {printable && (
        <button
          type="button"
          onClick={() => void openPdf(staffApi.walletReceiptPdfUrl(entry.id))}
          className="mt-0.5 shrink-0 rounded p-1 text-ink-faint transition hover:text-pine"
          aria-label="Print this receipt"
        >
          <Printer className="h-3 w-3" />
        </button>
      )}
    </li>
  );
}

export function WalletPanel({
  patientId,
  patientName,
  canWithdraw = false,
  onChanged,
  className,
}: {
  patientId: string;
  patientName?: string;
  /** Paying a balance back out is a refund, so it is not counter work. */
  canWithdraw?: boolean;
  onChanged?: (balancePaise: number) => void;
  className?: string;
}) {
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState<"deposit" | "withdraw" | null>(null);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [mode, setMode] = useState<PaymentMode>("cash");
  const [modeDetails, setModeDetails] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const found = await staffApi.wallet(patientId);
      setWallet(found);
      onChanged?.(found.balance_paise);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read the wallet.");
    }
    // onChanged is intentionally excluded: parents commonly pass an inline
    // arrow, and depending on it would refetch the wallet on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patientId]);

  useEffect(() => {
    void load();
  }, [load]);

  const reset = () => {
    setForm(null);
    setAmount("");
    setReason("");
    setMode("cash");
    setModeDetails({});
  };

  const submit = useCallback(async () => {
    const paise = rupeesToPaise(amount);
    if (!paise || paise <= 0) {
      setError("Enter an amount.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const entry =
        form === "deposit"
          ? await staffApi.walletDeposit(patientId, {
              amount_paise: paise,
              mode,
              mode_details: cleanModeDetails(modeDetails),
              reason: reason.trim() || null,
            })
          : await staffApi.walletWithdraw(patientId, {
              amount_paise: paise,
              reason: reason.trim(),
            });
      reset();
      await load();
      // The patient is handed paper for money that moved, every time.
      void openPdf(staffApi.walletReceiptPdfUrl(entry.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "That did not go through.");
    } finally {
      setBusy(false);
    }
  }, [amount, form, patientId, mode, modeDetails, reason, load]);

  const balance = wallet?.balance_paise ?? 0;

  return (
    <section className={cn("rounded-xl border border-pine/10 bg-white", className)}>
      <header className="flex items-center gap-2 border-b border-pine/10 px-3 py-2">
        <WalletIcon className="h-3.5 w-3.5 text-pine" />
        <h3 className="font-display text-xs font-semibold text-pine">
          Wallet{patientName ? ` · ${patientName}` : ""}
        </h3>
        <span
          className={cn(
            "tabular ml-auto rounded px-2 py-0.5 text-xs font-semibold",
            balance > 0 ? "bg-marigold/15 text-marigold-deep" : "bg-mint text-ink-faint"
          )}
        >
          {formatINR(balance)}
        </span>
      </header>

      {error && <p className="px-3 py-1.5 text-[11px] text-clay">{error}</p>}

      {form === null && (
        <div className="flex gap-1.5 px-3 py-2">
          <Button
            size="sm"
            variant="outline"
            className="h-7 flex-1 text-xs"
            onClick={() => setForm("deposit")}
          >
            Take advance
          </Button>
          {canWithdraw && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 flex-1 text-xs"
              disabled={balance <= 0}
              onClick={() => setForm("withdraw")}
            >
              Return balance
            </Button>
          )}
        </div>
      )}

      {form !== null && (
        <div className="space-y-2 px-3 py-2">
          <Input
            value={amount}
            inputMode="decimal"
            autoFocus
            onChange={(event) => setAmount(event.target.value)}
            placeholder={
              form === "withdraw" ? `Amount (up to ${formatINR(balance)})` : "Amount in ₹"
            }
            className="h-9 text-sm"
          />

          {form === "deposit" && (
            <>
              <div className="grid grid-cols-4 gap-1">
                {DEPOSIT_MODES.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => {
                      setMode(option.value);
                      setModeDetails({});
                    }}
                    className={cn(
                      "rounded border px-1 py-1 text-[11px] font-medium transition",
                      mode === option.value
                        ? "border-pine bg-pine text-white"
                        : "border-border text-ink-muted hover:bg-mint"
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <PaymentModeFields
                mode={mode}
                values={modeDetails}
                onChange={setModeDetails}
              />
            </>
          )}

          <Input
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={form === "withdraw" ? "Reason (required)" : "Note (optional)"}
            className="h-9 text-sm"
          />

          <div className="flex gap-1.5">
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={reset}>
              Cancel
            </Button>
            <Button
              size="sm"
              className="h-7 flex-1 text-xs"
              disabled={busy || (form === "withdraw" && reason.trim().length < 3)}
              onClick={() => void submit()}
            >
              {busy && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
              {form === "deposit" ? "Take advance" : "Return balance"}
            </Button>
          </div>
        </div>
      )}

      {wallet && wallet.entries.length > 0 && (
        <ul className="max-h-56 overflow-y-auto border-t border-border">
          {wallet.entries.map((entry) => (
            <EntryRow key={entry.id} entry={entry} />
          ))}
        </ul>
      )}
      {wallet && wallet.entries.length === 0 && (
        <p className="border-t border-border px-3 py-3 text-center text-[11px] text-ink-faint">
          Nothing on account yet.
        </p>
      )}
    </section>
  );
}
