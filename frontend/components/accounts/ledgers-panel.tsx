"use client";

/** The chart of accounts with balances, and one ledger's statement. */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Pencil, Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { AccountGroup, LedgerRow, LedgerStatement } from "@/lib/types/accounts";
import { VOUCHER_TYPE_LABEL, drCr, financialYearStart } from "@/lib/types/accounts";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import { formatDate, hospitalToday } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const SELECT = "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink";

interface LedgerForm {
  id?: string;
  name: string;
  code: string;
  group_id: string;
  opening: string;
  side: "dr" | "cr";
  is_active: boolean;
  is_system: boolean;
}

export function LedgersPanel({
  canManage, selectedId, onSelect,
}: {
  canManage: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const today = hospitalToday();
  const [ledgers, setLedgers] = useState<LedgerRow[]>([]);
  const [groups, setGroups] = useState<AccountGroup[]>([]);
  const [search, setSearch] = useState("");
  const [from, setFrom] = useState(financialYearStart(today));
  const [to, setTo] = useState(today);
  const [statement, setStatement] = useState<LedgerStatement | null>(null);
  const [form, setForm] = useState<LedgerForm | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [rows, groupRows] = await Promise.all([staffApi.ledgers(), staffApi.accountGroups()]);
      setLedgers(rows);
      setGroups(groupRows);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ledgers could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!selectedId) return;
    staffApi.ledgerStatement(selectedId, from, to).then(setStatement)
      .catch((err) => setError(err instanceof Error ? err.message : "The statement could not be loaded."));
  }, [selectedId, from, to]);

  const grouped = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const map = new Map<string, LedgerRow[]>();
    for (const ledger of ledgers) {
      if (needle && !`${ledger.name} ${ledger.code}`.toLowerCase().includes(needle)) continue;
      const list = map.get(ledger.group_path) ?? [];
      list.push(ledger);
      map.set(ledger.group_path, list);
    }
    return Array.from(map.entries());
  }, [ledgers, search]);

  async function save() {
    if (!form) return;
    setBusy(true);
    setError(null);
    try {
      const opening = rupeesToPaise(form.opening || "0");
      const saved = await staffApi.saveLedger({
        name: form.name.trim(), code: form.code.trim(), group_id: form.group_id,
        opening_balance_paise: form.side === "dr" ? opening : -opening, is_active: form.is_active, notes: null,
      }, form.id);
      setForm(null);
      await load();
      onSelect(saved.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The ledger could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  function edit(ledger: LedgerRow) {
    setForm({
      id: ledger.id, name: ledger.name, code: ledger.code, group_id: ledger.group_id,
      opening: String(Math.abs(ledger.opening_balance_paise) / 100), side: ledger.opening_balance_paise < 0 ? "cr" : "dr",
      is_active: ledger.is_active, is_system: ledger.is_system,
    });
  }

  return (
    <div className="grid gap-4 xl:grid-cols-[24rem_1fr]">
      {error && <p className="text-sm text-clay xl:col-span-2">{error}</p>}
      <Card className="h-fit">
        <CardHeader className="flex flex-row items-center justify-between gap-2 pb-2">
          <CardTitle>Ledgers</CardTitle>
          {canManage && !form && (
            <Button size="sm" variant="outline" onClick={() => setForm({
              name: "", code: "", group_id: groups[0]?.id ?? "", opening: "", side: "dr", is_active: true, is_system: false,
            })}>
              <Plus className="h-4 w-4" /> Add
            </Button>
          )}
        </CardHeader>
        <CardContent className="space-y-3">
          {form && (
            <div className="space-y-2 rounded-lg border border-border p-3 text-sm">
              <Input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <Input placeholder="Code, e.g. L-RENT" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} />
              <select className={SELECT} value={form.group_id} disabled={form.is_system}
                      onChange={(e) => setForm({ ...form, group_id: e.target.value })}>
                {groups.map((group) => <option key={group.id} value={group.id}>{group.name}</option>)}
              </select>
              <div className="flex gap-2">
                <Input placeholder="Opening balance ₹" inputMode="decimal" value={form.opening}
                       onChange={(e) => setForm({ ...form, opening: e.target.value })} />
                <select className={cn(SELECT, "w-20")} value={form.side}
                        onChange={(e) => setForm({ ...form, side: e.target.value as "dr" | "cr" })}>
                  <option value="dr">Dr</option>
                  <option value="cr">Cr</option>
                </select>
              </div>
              {!form.is_system && (
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />
                  Open for entries
                </label>
              )}
              {form.is_system && <p className="text-xs text-ink-muted">The posting engine writes to this ledger: rename it or set its opening balance only.</p>}
              <div className="flex gap-2">
                <Button size="sm" disabled={busy || form.name.trim().length < 2 || !form.code.trim() || !form.group_id}
                        onClick={() => void save()}>
                  {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setForm(null)}>Cancel</Button>
              </div>
            </div>
          )}
          <Input placeholder="Find a ledger" value={search} onChange={(e) => setSearch(e.target.value)} />
          <div className="max-h-[60vh] space-y-3 overflow-y-auto">
            {grouped.map(([path, rows]) => (
              <div key={path}>
                <p className="px-1 text-[11px] uppercase tracking-wide text-ink-faint">{path}</p>
                <ul>
                  {rows.map((ledger) => (
                    <li key={ledger.id}>
                      <button onClick={() => onSelect(ledger.id)}
                              className={cn("flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-mint",
                                selectedId === ledger.id && "bg-mint font-medium")}>
                        <span className="truncate">{ledger.name}{!ledger.is_active && " (closed)"}</span>
                        <span className="tabular shrink-0 text-xs text-ink-muted">{drCr(ledger.balance_paise, formatINR)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-2">
          <CardTitle className="flex items-center gap-2">
            {statement ? statement.ledger.name : "Select a ledger"}
            {statement?.ledger.is_system && <Badge variant="outline">System</Badge>}
            {statement && canManage && (
              <Button size="sm" variant="ghost" aria-label="Edit ledger" onClick={() => edit(statement.ledger)}>
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Input type="date" className="w-40" value={from} onChange={(e) => setFrom(e.target.value)} />
            <span className="text-ink-muted">to</span>
            <Input type="date" className="w-40" value={to} onChange={(e) => setTo(e.target.value)} />
          </div>
        </CardHeader>
        <CardContent className="overflow-x-auto p-0">
          {statement && (
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-border bg-mint/50 text-left text-xs uppercase tracking-wide text-ink-faint">
                  <th className="px-4 py-2">Date</th>
                  <th className="px-4 py-2">Voucher</th>
                  <th className="px-4 py-2">Narration</th>
                  <th className="px-4 py-2 text-right">Debit</th>
                  <th className="px-4 py-2 text-right">Credit</th>
                  <th className="px-4 py-2 text-right">Balance</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-border bg-mint/20">
                  <td className="px-4 py-2" colSpan={5}>Opening balance on {formatDate(statement.date_from)}</td>
                  <td className="tabular px-4 py-2 text-right">{drCr(statement.opening_paise, formatINR)}</td>
                </tr>
                {statement.rows.map((row, index) => (
                  <tr key={`${row.voucher_id}-${index}`} className="border-b border-border last:border-0">
                    <td className="px-4 py-2 whitespace-nowrap">{formatDate(row.voucher_date)}</td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      {row.voucher_number}
                      <span className="block text-xs text-ink-muted">{VOUCHER_TYPE_LABEL[row.voucher_type]}{row.status === "reversed" ? " · reversed" : ""}</span>
                    </td>
                    <td className="px-4 py-2 text-ink-muted">{row.narration}</td>
                    <td className="tabular px-4 py-2 text-right">{row.debit_paise ? formatINR(row.debit_paise) : ""}</td>
                    <td className="tabular px-4 py-2 text-right">{row.credit_paise ? formatINR(row.credit_paise) : ""}</td>
                    <td className="tabular px-4 py-2 text-right">{drCr(row.balance_paise, formatINR)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-pine/20 font-semibold">
                  <td className="px-4 py-2" colSpan={3}>Closing balance on {formatDate(statement.date_to)}</td>
                  <td className="tabular px-4 py-2 text-right">{formatINR(statement.total_debit_paise)}</td>
                  <td className="tabular px-4 py-2 text-right">{formatINR(statement.total_credit_paise)}</td>
                  <td className="tabular px-4 py-2 text-right">{drCr(statement.closing_paise, formatINR)}</td>
                </tr>
              </tfoot>
            </table>
          )}
          {!statement && <p className="px-4 pb-6 text-sm text-ink-muted">Choose a ledger to see its entries.</p>}
        </CardContent>
      </Card>
    </div>
  );
}
