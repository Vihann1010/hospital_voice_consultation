"use client";

/**
 * The day book: every voucher, and manual vouchers for what the counter does
 * not record — rent, salaries, bank charges, opening entries.
 *
 * A voucher posted from a bill or receipt cannot be reversed here: it is
 * corrected at its source, and the books follow on the next posting run.
 */
import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Loader2, Plus, Trash2 } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { LedgerRow, VoucherDetail, VoucherRow } from "@/lib/types/accounts";
import { VOUCHER_TYPE_LABEL, financialYearStart } from "@/lib/types/accounts";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import { formatDate, hospitalToday } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SELECT = "h-9 rounded-md border border-border bg-white px-2 text-sm text-ink";

interface DraftLine { ledger_id: string; debit: string; credit: string }

export function DayBookPanel({ canManage }: { canManage: boolean }) {
  const today = hospitalToday();
  const [from, setFrom] = useState(today.slice(0, 8) + "01");
  const [to, setTo] = useState(today);
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<VoucherRow[]>([]);
  const [open, setOpen] = useState<Record<string, VoucherDetail>>({});
  const [ledgers, setLedgers] = useState<LedgerRow[]>([]);
  const [composing, setComposing] = useState(false);
  const [vType, setVType] = useState("journal");
  const [vDate, setVDate] = useState(today);
  const [narration, setNarration] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([{ ledger_id: "", debit: "", credit: "" }, { ledger_id: "", debit: "", credit: "" }]);
  const [reversing, setReversing] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setRows(await staffApi.vouchers({ from, to, type: type || undefined, q: q.trim() || undefined }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Vouchers could not be loaded.");
    }
  }, [from, to, type, q]);

  useEffect(() => {
    const timer = setTimeout(() => void load(), 250);
    return () => clearTimeout(timer);
  }, [load]);

  useEffect(() => {
    if (composing && ledgers.length === 0) void staffApi.ledgers().then((all) => setLedgers(all.filter((l) => l.is_active)));
  }, [composing, ledgers.length]);

  async function toggle(row: VoucherRow) {
    if (open[row.id]) {
      const next = { ...open };
      delete next[row.id];
      setOpen(next);
      return;
    }
    const detail = await staffApi.voucher(row.id);
    setOpen({ ...open, [row.id]: detail });
  }

  const debit = lines.reduce((sum, line) => sum + rupeesToPaise(line.debit || "0"), 0);
  const credit = lines.reduce((sum, line) => sum + rupeesToPaise(line.credit || "0"), 0);
  const ready = narration.trim().length >= 3 && debit > 0 && debit === credit
    && lines.every((line) => line.ledger_id && ((rupeesToPaise(line.debit || "0") > 0) !== (rupeesToPaise(line.credit || "0") > 0)));

  async function postVoucher() {
    setBusy(true);
    setError(null);
    try {
      await staffApi.createVoucher({
        voucher_type: vType, voucher_date: vDate, narration: narration.trim(),
        lines: lines.map((line) => ({ ledger_id: line.ledger_id, debit_paise: rupeesToPaise(line.debit || "0"),
                                      credit_paise: rupeesToPaise(line.credit || "0") })),
      });
      setComposing(false);
      setNarration("");
      setLines([{ ledger_id: "", debit: "", credit: "" }, { ledger_id: "", debit: "", credit: "" }]);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The voucher could not be posted.");
    } finally {
      setBusy(false);
    }
  }

  async function reverse(id: string) {
    setBusy(true);
    setError(null);
    try {
      await staffApi.reverseVoucher(id, reason.trim());
      setReversing(null);
      setReason("");
      setOpen({});
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The voucher could not be reversed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-clay">{error}</p>}
      {composing && (
        <Card>
          <CardHeader className="pb-2"><CardTitle>New voucher</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">
              <select className={SELECT} value={vType} onChange={(e) => setVType(e.target.value)}>
                {["journal", "payment", "receipt", "contra"].map((t) => <option key={t} value={t}>{VOUCHER_TYPE_LABEL[t]}</option>)}
              </select>
              <Input type="date" className="w-40" value={vDate} max={today} onChange={(e) => setVDate(e.target.value)} />
              <Input className="min-w-[16rem] flex-1" placeholder="Narration: what this is for" value={narration}
                     onChange={(e) => setNarration(e.target.value)} />
            </div>
            {lines.map((line, index) => (
              <div key={index} className="flex flex-wrap items-center gap-2">
                <select className={`${SELECT} min-w-[16rem] flex-1`} value={line.ledger_id}
                        onChange={(e) => setLines(lines.map((l, i) => i === index ? { ...l, ledger_id: e.target.value } : l))}>
                  <option value="">Ledger…</option>
                  {ledgers.map((ledger) => <option key={ledger.id} value={ledger.id}>{ledger.name}</option>)}
                </select>
                <Input className="w-32" placeholder="Debit ₹" inputMode="decimal" value={line.debit}
                       onChange={(e) => setLines(lines.map((l, i) => i === index ? { ...l, debit: e.target.value, credit: e.target.value ? "" : l.credit } : l))} />
                <Input className="w-32" placeholder="Credit ₹" inputMode="decimal" value={line.credit}
                       onChange={(e) => setLines(lines.map((l, i) => i === index ? { ...l, credit: e.target.value, debit: e.target.value ? "" : l.debit } : l))} />
                <Button size="sm" variant="ghost" aria-label="Remove line" disabled={lines.length <= 2}
                        onClick={() => setLines(lines.filter((_, i) => i !== index))}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            ))}
            <div className="flex flex-wrap items-center gap-3">
              <Button size="sm" variant="outline" onClick={() => setLines([...lines, { ledger_id: "", debit: "", credit: "" }])}>
                <Plus className="h-4 w-4" /> Line
              </Button>
              <span className={debit === credit ? "text-ink-muted" : "font-medium text-clay"}>
                Debits {formatINR(debit)} · Credits {formatINR(credit)}
                {debit !== credit && ` · differ by ${formatINR(Math.abs(debit - credit))}`}
              </span>
            </div>
            <div className="flex gap-2">
              <Button size="sm" disabled={busy || !ready} onClick={() => void postVoucher()}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Post voucher
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setComposing(false)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-2">
          <CardTitle>Day book</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Input type="date" className="w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
            <Input type="date" className="w-40" value={to} onChange={(e) => setTo(e.target.value)} />
            <select className={SELECT} value={type} onChange={(e) => setType(e.target.value)}>
              <option value="">All types</option>
              {Object.entries(VOUCHER_TYPE_LABEL).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
            </select>
            <Input className="w-44" placeholder="Number or narration" value={q} onChange={(e) => setQ(e.target.value)} />
            {canManage && !composing && (
              <Button size="sm" variant="outline" onClick={() => setComposing(true)}><Plus className="h-4 w-4" /> Voucher</Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-border bg-mint/50 text-left text-xs uppercase tracking-wide text-ink-faint">
                <th className="w-6 px-2 py-2" />
                <th className="px-3 py-2">Date</th>
                <th className="px-3 py-2">Voucher</th>
                <th className="px-3 py-2">Narration</th>
                <th className="px-3 py-2 text-right">Amount</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-ink-muted">No vouchers in this period.</td></tr>
              )}
              {rows.map((row) => (
                <FragmentRow key={row.id} row={row} detail={open[row.id]} onToggle={() => void toggle(row)}>
                  {open[row.id] && (
                    <div className="space-y-2">
                      <table className="w-full text-xs">
                        <tbody>
                          {open[row.id].lines.map((line, index) => (
                            <tr key={index}>
                              <td className="py-0.5">{line.debit_paise ? line.ledger_name : <span className="pl-6">To {line.ledger_name}</span>}</td>
                              <td className="tabular py-0.5 text-right">{line.debit_paise ? formatINR(line.debit_paise) : ""}</td>
                              <td className="tabular py-0.5 text-right">{line.credit_paise ? formatINR(line.credit_paise) : ""}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {row.reversal_reason && <p className="text-xs text-ink-muted">Reversed by {row.reversed_by_name}: {row.reversal_reason}</p>}
                      {canManage && row.is_manual && row.status === "posted" && !row.reversal_of_id && (
                        reversing === row.id ? (
                          <div className="flex flex-wrap gap-2">
                            <Input className="w-72" placeholder="Reason for reversing" value={reason} onChange={(e) => setReason(e.target.value)} />
                            <Button size="sm" disabled={busy || reason.trim().length < 3} onClick={() => void reverse(row.id)}>Reverse</Button>
                            <Button size="sm" variant="ghost" onClick={() => setReversing(null)}>Cancel</Button>
                          </div>
                        ) : (
                          <Button size="sm" variant="outline" onClick={() => setReversing(row.id)}>Reverse this voucher</Button>
                        )
                      )}
                    </div>
                  )}
                </FragmentRow>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function FragmentRow({
  row, detail, onToggle, children,
}: {
  row: VoucherRow;
  detail?: VoucherDetail;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <>
      <tr className="cursor-pointer border-b border-border hover:bg-mint/40" onClick={onToggle}>
        <td className="px-2 py-2 text-ink-faint">{detail ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}</td>
        <td className="px-3 py-2 whitespace-nowrap">{formatDate(row.voucher_date)}</td>
        <td className="px-3 py-2 whitespace-nowrap">
          {row.voucher_number}
          <span className="ml-2 inline-flex gap-1">
            <Badge variant="outline">{VOUCHER_TYPE_LABEL[row.voucher_type]}</Badge>
            {row.status === "reversed" && <Badge variant="outline" className="text-clay">Reversed</Badge>}
            {row.reversal_of_id && <Badge variant="outline">Reversal</Badge>}
            {row.is_manual && <Badge variant="outline">Manual</Badge>}
          </span>
        </td>
        <td className="px-3 py-2 text-ink-muted">{row.narration}</td>
        <td className="tabular px-3 py-2 text-right">{formatINR(row.total_paise)}</td>
      </tr>
      {detail && (
        <tr className="border-b border-border bg-mint/20">
          <td />
          <td colSpan={4} className="px-3 py-2">{children}</td>
        </tr>
      )}
    </>
  );
}
