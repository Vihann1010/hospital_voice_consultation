"use client";

/**
 * The price list: what each service costs.
 *
 * Repricing changes what the counter charges from the next bill onward. Bills
 * already raised keep the rate that applied when they were raised, so a
 * correction to a past bill is an amendment, not a reprice.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Pencil, Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { ServiceCategory, ServiceItem } from "@/lib/types/emr";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import { DEPARTMENTS } from "@/lib/types/core";
import { DEPARTMENT_LABEL } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SELECT = "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink";
const CATEGORIES: ServiceCategory[] = ["consultation", "procedure", "investigation", "registration", "other"];
const CATEGORY_LABEL: Record<string, string> = {
  consultation: "Consultation",
  procedure: "Procedure",
  investigation: "Investigation",
  registration: "Registration",
  other: "Other",
};

interface Form {
  code: string;
  existing: boolean;
  name: string;
  category: ServiceCategory;
  department: string;
  rate: string;
  tax_percent: string;
  hsn_sac_code: string;
  is_active: boolean;
}

const EMPTY: Form = {
  code: "", existing: false, name: "", category: "procedure", department: "",
  rate: "", tax_percent: "0", hsn_sac_code: "", is_active: true,
};

export function PriceList({ canEdit }: { canEdit: boolean }) {
  const [items, setItems] = useState<ServiceItem[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setItems(await staffApi.serviceItems(false));
  }, []);

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [load]);

  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return items.filter(
      (item) =>
        (!category || item.category === category) &&
        (!needle || `${item.code} ${item.name}`.toLowerCase().includes(needle))
    );
  }, [items, search, category]);

  const problem =
    form &&
    (!form.code.trim()
      ? "Give the service a code."
      : form.name.trim().length < 2
        ? "Give the service a name."
        : form.rate.trim() === "" || rupeesToPaise(form.rate) < 0
          ? "Enter the rate."
          : null);

  async function save() {
    if (!form || problem) return;
    setBusy(true);
    setError(null);
    try {
      await staffApi.saveService(form.code.trim().toUpperCase(), {
        code: form.code.trim().toUpperCase(),
        name: form.name.trim(),
        category: form.category,
        department: form.department || null,
        rate_paise: rupeesToPaise(form.rate),
        tax_percent: Number(form.tax_percent) || 0,
        hsn_sac_code: form.hsn_sac_code.trim() || null,
        is_active: form.is_active,
      });
      setForm(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The service could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const set = (patch: Partial<Form>) => form && setForm({ ...form, ...patch });

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-clay">{error}</p>}

      {form && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>{form.existing ? `Reprice ${form.code}` : "Add a service"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Code</span>
                <Input value={form.code} disabled={form.existing} placeholder="OPD-ORTHO-NEW"
                       onChange={(event) => set({ code: event.target.value.toUpperCase() })} />
              </label>
              <label className="space-y-1 sm:col-span-2">
                <span className="text-xs text-ink-muted">Name, as it prints on the bill</span>
                <Input value={form.name} onChange={(event) => set({ name: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Kind</span>
                <select className={SELECT} value={form.category}
                        onChange={(event) => set({ category: event.target.value as ServiceCategory })}>
                  {CATEGORIES.map((item) => <option key={item} value={item}>{CATEGORY_LABEL[item]}</option>)}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Department</span>
                <select className={SELECT} value={form.department}
                        onChange={(event) => set({ department: event.target.value })}>
                  <option value="">Any department</option>
                  {DEPARTMENTS.map((dept) => (
                    <option key={dept} value={dept}>{DEPARTMENT_LABEL[dept] ?? dept}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Rate (Rs)</span>
                <Input inputMode="decimal" value={form.rate}
                       onChange={(event) => set({ rate: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">GST %</span>
                <Input type="number" min={0} max={28} value={form.tax_percent}
                       onChange={(event) => set({ tax_percent: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">HSN / SAC code</span>
                <Input value={form.hsn_sac_code}
                       onChange={(event) => set({ hsn_sac_code: event.target.value })} />
              </label>
              <label className="flex items-end gap-2 pb-1.5">
                <input type="checkbox" checked={form.is_active}
                       onChange={(event) => set({ is_active: event.target.checked })} />
                <span>Offered at the counter</span>
              </label>
            </div>
            <p className="text-xs text-ink-muted">
              Bills already raised keep their old rate. This changes what is charged from the next bill.
            </p>
            {problem && <p className="text-xs text-clay">{problem}</p>}
            <div className="flex gap-2">
              <Button size="sm" disabled={busy || Boolean(problem)} onClick={() => void save()}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setForm(null)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-2">
          <CardTitle>Services</CardTitle>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <Input className="h-9 w-56" placeholder="Search code or name" value={search}
                   onChange={(event) => setSearch(event.target.value)} />
            <select className="h-9 rounded-md border border-border bg-white px-2 text-sm" value={category}
                    onChange={(event) => setCategory(event.target.value)} aria-label="Kind">
              <option value="">Every kind</option>
              {CATEGORIES.map((item) => <option key={item} value={item}>{CATEGORY_LABEL[item]}</option>)}
            </select>
            {canEdit && !form && (
              <Button size="sm" variant="outline" onClick={() => setForm({ ...EMPTY })}>
                <Plus className="h-4 w-4" /> Add service
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {shown.length === 0 ? (
            <p className="text-sm text-ink-muted">No services match.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="text-left text-xs text-ink-muted">
                  <tr>
                    <th className="py-2 pr-3">Code</th>
                    <th className="py-2 pr-3">Service</th>
                    <th className="py-2 pr-3">Kind</th>
                    <th className="py-2 pr-3">Department</th>
                    <th className="py-2 pr-3 text-right">Rate</th>
                    <th className="py-2 pr-3 text-right">GST</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {shown.map((item) => (
                    <tr key={item.id} className={item.is_active ? "" : "text-ink-muted"}>
                      <td className="py-2 pr-3 font-mono text-xs">{item.code}</td>
                      <td className="py-2 pr-3">
                        {item.name}
                        {!item.is_active && <Badge variant="outline" className="ml-2">Not offered</Badge>}
                      </td>
                      <td className="py-2 pr-3">{CATEGORY_LABEL[item.category] ?? item.category}</td>
                      <td className="py-2 pr-3">
                        {item.department ? DEPARTMENT_LABEL[item.department] ?? item.department : "Any"}
                      </td>
                      <td className="py-2 pr-3 text-right tabular-nums">{formatINR(item.rate_paise)}</td>
                      <td className="py-2 pr-3 text-right">{item.tax_percent}%</td>
                      <td className="py-2 text-right">
                        {canEdit && (
                          <Button size="sm" variant="ghost" aria-label={`Edit ${item.name}`}
                                  onClick={() => setForm({
                                    code: item.code, existing: true, name: item.name, category: item.category,
                                    department: item.department ?? "", rate: String(item.rate_paise / 100),
                                    tax_percent: String(item.tax_percent), hsn_sac_code: "",
                                    is_active: item.is_active,
                                  })}>
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
