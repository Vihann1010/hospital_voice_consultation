"use client";

/**
 * The patient diary.
 *
 * One patient's whole money history — OPD bills, inpatient stays and counter
 * advances — as a single ledger with a running balance. It exists to answer
 * one question staff are asked all day: what does this patient owe?
 *
 * Two things are deliberately not netted together. **Outstanding** is what
 * the patient owes; **wallet** is what they have left on account. They sit
 * side by side because offsetting them hides both — a patient with ₹2,000 on
 * account and a ₹500 unpaid bill has two facts, not one, and the counter
 * needs to see the bill in order to settle it from the credit.
 *
 * Cancelled bills stay in the list, struck out and excluded from every
 * total. A patient holding a cancelled bill needs to be able to find it;
 * hiding it makes this screen disagree with the paper in their hand.
 */
import { useCallback, useEffect, useState } from "react";
import {
  BedDouble,
  FileText,
  Loader2,
  Printer,
  Search,
  Wallet as WalletIcon,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { getToken } from "@/lib/auth";
import type { DiaryEntry, PatientCard, PatientDiary } from "@/lib/types/emr";
import { formatINR } from "@/lib/types/emr";
import { formatDate } from "@/lib/format";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const KIND_ICON = {
  opd: FileText,
  ipd: BedDouble,
  wallet: WalletIcon,
} as const;

async function openPdf(url: string) {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
  });
  if (!response.ok) return;
  const blobUrl = URL.createObjectURL(await response.blob());
  window.open(blobUrl, "_blank");
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
}

function Stat({
  label,
  value,
  tone = "plain",
  hint,
}: {
  label: string;
  value: string;
  tone?: "plain" | "owed" | "credit";
  hint?: string;
}) {
  return (
    <div
      className={cn(
        "rounded-lg border px-3 py-2",
        tone === "owed" && "border-clay/25 bg-clay/5",
        tone === "credit" && "border-marigold-deep/25 bg-marigold/10",
        tone === "plain" && "border-border bg-white"
      )}
    >
      <p className="text-[10px] uppercase tracking-wide text-ink-faint">{label}</p>
      <p
        className={cn(
          "tabular font-display text-lg font-semibold",
          tone === "owed" && "text-clay",
          tone === "credit" && "text-marigold-deep",
          tone === "plain" && "text-pine"
        )}
      >
        {value}
      </p>
      {hint && <p className="text-[10px] text-ink-faint">{hint}</p>}
    </div>
  );
}

function Row({ entry }: { entry: DiaryEntry }) {
  const Icon = KIND_ICON[entry.kind] ?? FileText;
  return (
    <li
      className={cn(
        "grid grid-cols-[16px_118px_1fr_repeat(4,minmax(0,84px))] items-center gap-2 border-b",
        "border-border px-3 py-2 text-xs last:border-b-0",
        entry.cancelled && "opacity-45"
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0 text-ink-faint" />

      <div className="min-w-0">
        <p className={cn("truncate font-medium text-ink", entry.cancelled && "line-through")}>
          {entry.reference}
        </p>
        <p className="text-[10px] text-ink-faint">{formatDate(entry.date)}</p>
      </div>

      <div className="min-w-0">
        <p className="truncate text-ink-muted">{entry.description}</p>
        <p className="flex flex-wrap gap-1 text-[10px]">
          {entry.cancelled && <span className="text-clay">cancelled</span>}
          {entry.credited_to_ipd && (
            <span className="rounded bg-mint px-1 text-pine">credited to IPD</span>
          )}
          {entry.notes.map((note) => (
            <span key={note} className="text-marigold-deep">
              {note}
            </span>
          ))}
        </p>
      </div>

      <span className="tabular text-right text-ink">
        {entry.net_paise ? formatINR(entry.net_paise) : "—"}
      </span>
      <span className="tabular text-right text-ink-muted">
        {entry.received_paise ? formatINR(entry.received_paise) : "—"}
      </span>
      <span className="tabular text-right text-clay">
        {entry.refunded_paise ? formatINR(entry.refunded_paise) : "—"}
      </span>
      <span className="tabular text-right font-medium text-pine">
        {formatINR(entry.running_balance_paise)}
      </span>
    </li>
  );
}

export function PatientDiaryView({ patientId }: { patientId?: string }) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<PatientCard[]>([]);
  const [chosenId, setChosenId] = useState<string | undefined>(patientId);
  const [diary, setDiary] = useState<PatientDiary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const query = term.trim();
    if (query.length < 2) {
      setResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        setResults(await staffApi.searchCounterPatients(query));
      } catch {
        setResults([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [term]);

  const load = useCallback(async (id: string) => {
    setLoading(true);
    setError(null);
    try {
      setDiary(await staffApi.patientDiary(id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the diary.");
      setDiary(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (chosenId) void load(chosenId);
  }, [chosenId, load]);

  const totals = diary?.totals;

  return (
    <div className="space-y-4">
      <div className="relative max-w-md">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="UHID, phone or name"
          className="h-9 pl-8 text-sm"
          autoFocus
        />
        {results.length > 0 && (
          <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-border bg-white shadow-card">
            {results.map((patient) => (
              <li key={patient.id}>
                <button
                  type="button"
                  onClick={() => {
                    setChosenId(patient.id);
                    setResults([]);
                    setTerm("");
                  }}
                  className="flex w-full items-baseline gap-2 border-b border-border px-3 py-1.5 text-left last:border-b-0 hover:bg-mint"
                >
                  <span className="text-sm text-ink">{patient.name}</span>
                  <span className="text-[11px] text-ink-faint">
                    {patient.uhid} · {patient.phone_number}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {loading && (
        <p className="flex items-center gap-1.5 text-xs text-ink-faint">
          <Loader2 className="h-3 w-3 animate-spin" /> Reading the history…
        </p>
      )}
      {error && <p className="text-xs text-clay">{error}</p>}

      {!diary && !loading && !error && (
        <p className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-xs text-ink-muted">
          Find a patient to see everything they have been charged and have paid.
        </p>
      )}

      {diary && totals && (
        <>
          <div className="rounded-xl border border-pine/10 bg-white p-4">
            <div className="flex flex-wrap items-baseline gap-2">
              <h2 className="font-display text-lg font-semibold text-pine">
                {diary.patient.name}
              </h2>
              <span className="text-xs text-ink-faint">
                {diary.patient.uhid} · {diary.patient.age} · {diary.patient.gender} ·{" "}
                {diary.patient.phone_number}
              </span>
            </div>

            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
              <Stat label="Billed" value={formatINR(totals.net_paise)} />
              <Stat label="Received" value={formatINR(totals.received_paise)} />
              <Stat label="Refunded" value={formatINR(totals.refunded_paise)} />
              <Stat
                label="Outstanding"
                value={formatINR(totals.outstanding_paise)}
                tone={totals.outstanding_paise > 0 ? "owed" : "plain"}
                hint={totals.outstanding_paise > 0 ? "still to collect" : "nothing due"}
              />
              <Stat
                label="On account"
                value={formatINR(totals.wallet_balance_paise)}
                tone={totals.wallet_balance_paise > 0 ? "credit" : "plain"}
                hint="not offset against what is owed"
              />
            </div>

            <p className="mt-2 text-[11px] text-ink-faint">
              {totals.visit_count} bill{totals.visit_count === 1 ? "" : "s"}
              {totals.admission_count > 0 &&
                ` · ${totals.admission_count} admission${
                  totals.admission_count === 1 ? "" : "s"
                }`}
            </p>
          </div>

          <div className="rounded-xl border border-pine/10 bg-white">
            <div
              className="grid grid-cols-[16px_118px_1fr_repeat(4,minmax(0,84px))] gap-2 border-b
                         border-pine/10 px-3 py-2 text-[10px] uppercase tracking-wide text-ink-faint"
            >
              <span />
              <span>Reference</span>
              <span>Detail</span>
              <span className="text-right">Net</span>
              <span className="text-right">Received</span>
              <span className="text-right">Refunded</span>
              <span className="text-right">Balance</span>
            </div>

            {diary.entries.length === 0 ? (
              <p className="px-3 py-8 text-center text-xs text-ink-faint">
                Nothing on record yet.
              </p>
            ) : (
              <ul className="max-h-[calc(100vh-420px)] overflow-y-auto">
                {diary.entries.map((entry) => (
                  <Row key={`${entry.kind}-${entry.reference}-${entry.date}`} entry={entry} />
                ))}
              </ul>
            )}

            <div className="flex flex-wrap gap-1.5 border-t border-border px-3 py-2">
              {diary.entries
                .filter((entry) => entry.invoice_id && !entry.cancelled)
                .slice(0, 4)
                .map((entry) => (
                  <button
                    key={entry.reference}
                    type="button"
                    onClick={() =>
                      void openPdf(
                        `${staffApi.invoicePdfUrl(entry.invoice_id as string)}?duplicate=true`
                      )
                    }
                    className="flex items-center gap-1 rounded border border-border px-2 py-1
                               text-[11px] text-ink-muted transition hover:border-pine hover:text-pine"
                  >
                    <Printer className="h-3 w-3" />
                    {entry.reference}
                  </button>
                ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
