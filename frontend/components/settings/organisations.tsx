"use client";

/**
 * Insurers, TPAs, employers and schemes — and the rates agreed with them.
 *
 * A rate card is sent whole, the way it arrives from the payer: a renegotiated
 * sheet, not three amendments. Saving replaces the card, so a service dropped
 * from the agreement stops being charged at the old agreed rate.
 */
import { useCallback, useEffect, useState } from "react";
import { Loader2, Pencil, Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { Organisation, ServiceItem } from "@/lib/types/emr";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import { PAYER_TYPE_LABEL } from "@/lib/types/insurance";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SELECT = "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink";
const PAYER_TYPES = ["insurance", "tpa", "corporate", "government_scheme"];

interface Form {
  id?: string;
  code: string;
  name: string;
  payer_type: string;
  contact_person: string;
  phone_number: string;
  email: string;
  address: string;
  default_discount_percent: string;
  credit_days: string;
  is_active: boolean;
}

const EMPTY: Form = {
  code: "", name: "", payer_type: "tpa", contact_person: "", phone_number: "", email: "",
  address: "", default_discount_percent: "0", credit_days: "0", is_active: true,
};

export function Organisations({ canEdit }: { canEdit: boolean }) {
  const [organisations, setOrganisations] = useState<Organisation[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [rateCardFor, setRateCardFor] = useState<Organisation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setOrganisations(await staffApi.organisations(false));
  }, []);

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [load]);

  const problem =
    form &&
    (!/^[A-Za-z0-9_-]{2,32}$/.test(form.code.trim())
      ? "The code is 2 to 32 letters, numbers, dash or underscore."
      : form.name.trim().length < 2
        ? "Give the payer a name."
        : null);

  async function save() {
    if (!form || problem) return;
    setBusy(true);
    setError(null);
    try {
      await staffApi.saveOrganisation(
        {
          code: form.code.trim(),
          name: form.name.trim(),
          payer_type: form.payer_type,
          contact_person: form.contact_person.trim() || null,
          phone_number: form.phone_number.trim() || null,
          email: form.email.trim() || null,
          address: form.address.trim() || null,
          default_discount_percent: Number(form.default_discount_percent) || 0,
          credit_days: Number(form.credit_days) || 0,
          is_active: form.is_active,
        },
        form.id
      );
      setForm(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The payer could not be saved.");
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
            <CardTitle>{form.id ? `Edit ${form.name}` : "Add a payer"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Short code</span>
                <Input value={form.code} placeholder="STAR-HEALTH"
                       onChange={(event) => set({ code: event.target.value })} />
              </label>
              <label className="space-y-1 sm:col-span-2">
                <span className="text-xs text-ink-muted">Name</span>
                <Input value={form.name} onChange={(event) => set({ name: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Kind of payer</span>
                <select className={SELECT} value={form.payer_type}
                        onChange={(event) => set({ payer_type: event.target.value })}>
                  {PAYER_TYPES.map((type) => (
                    <option key={type} value={type}>{PAYER_TYPE_LABEL[type] ?? type}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Contact person</span>
                <Input value={form.contact_person}
                       onChange={(event) => set({ contact_person: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Phone</span>
                <Input value={form.phone_number} inputMode="tel"
                       onChange={(event) => set({ phone_number: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Email</span>
                <Input value={form.email} onChange={(event) => set({ email: event.target.value })} />
              </label>
              <label className="space-y-1 sm:col-span-2">
                <span className="text-xs text-ink-muted">Address</span>
                <Input value={form.address} onChange={(event) => set({ address: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Standard discount %</span>
                <Input type="number" min={0} max={100} value={form.default_discount_percent}
                       onChange={(event) => set({ default_discount_percent: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Credit days</span>
                <Input type="number" min={0} max={365} value={form.credit_days}
                       onChange={(event) => set({ credit_days: event.target.value })} />
              </label>
              <label className="flex items-end gap-2 pb-1.5">
                <input type="checkbox" checked={form.is_active}
                       onChange={(event) => set({ is_active: event.target.checked })} />
                <span>In use</span>
              </label>
            </div>
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
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle>Insurers, TPAs and employers</CardTitle>
          {canEdit && !form && (
            <Button size="sm" variant="outline" onClick={() => setForm({ ...EMPTY })}>
              <Plus className="h-4 w-4" /> Add payer
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {organisations.length === 0 ? (
            <p className="text-sm text-ink-muted">
              No payers yet. An insurance claim can only name a payer listed here.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="text-left text-xs text-ink-muted">
                  <tr>
                    <th className="py-2 pr-3">Code</th>
                    <th className="py-2 pr-3">Payer</th>
                    <th className="py-2 pr-3">Kind</th>
                    <th className="py-2 pr-3">Contact</th>
                    <th className="py-2 pr-3 text-right">Discount</th>
                    <th className="py-2 pr-3 text-right">Credit days</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {organisations.map((org) => (
                    <tr key={org.id} className={org.is_active ? "" : "text-ink-muted"}>
                      <td className="py-2 pr-3 font-mono text-xs">{org.code}</td>
                      <td className="py-2 pr-3">
                        {org.name}
                        {!org.is_active && <Badge variant="outline" className="ml-2">Not in use</Badge>}
                      </td>
                      <td className="py-2 pr-3">{PAYER_TYPE_LABEL[org.payer_type] ?? org.payer_type}</td>
                      <td className="py-2 pr-3 text-xs text-ink-muted">{org.contact_person || "—"}</td>
                      <td className="py-2 pr-3 text-right">{org.default_discount_percent}%</td>
                      <td className="py-2 pr-3 text-right">{org.credit_days}</td>
                      <td className="py-2 text-right">
                        <Button size="sm" variant="ghost" onClick={() => setRateCardFor(org)}>Rates</Button>
                        {canEdit && (
                          <Button size="sm" variant="ghost" aria-label={`Edit ${org.name}`}
                                  onClick={() => setForm({
                                    id: org.id, code: org.code, name: org.name, payer_type: org.payer_type,
                                    contact_person: org.contact_person ?? "",
                                    phone_number: org.phone_number ?? "", email: org.email ?? "", address: "",
                                    default_discount_percent: String(org.default_discount_percent),
                                    credit_days: String(org.credit_days), is_active: org.is_active,
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

      {rateCardFor && (
        <RateCard organisation={rateCardFor} canEdit={canEdit} onClose={() => setRateCardFor(null)} />
      )}
    </div>
  );
}

function RateCard({
  organisation, canEdit, onClose,
}: { organisation: Organisation; canEdit: boolean; onClose: () => void }) {
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [rates, setRates] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setSaved(null);
    Promise.all([staffApi.serviceItems(true), staffApi.organisationRates(organisation.id)])
      .then(([list, agreed]) => {
        if (!live) return;
        setServices(list);
        setRates(Object.fromEntries(agreed.map((rate) => [rate.service_item_id, String(rate.rate_paise / 100)])));
      })
      .catch((err) => live && setError(err instanceof Error ? err.message : "The rate card could not be loaded."));
    return () => { live = false; };
  }, [organisation.id]);

  const agreed = Object.values(rates).filter((value) => value.trim() !== "").length;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const card = Object.entries(rates)
        .filter(([, value]) => value.trim() !== "")
        .map(([service_item_id, value]) => ({ service_item_id, rate_paise: rupeesToPaise(value) }));
      await staffApi.saveOrganisationRates(organisation.id, card);
      setSaved(`${card.length} agreed ${card.length === 1 ? "rate" : "rates"} saved.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The rate card could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const shown = services.filter(
    (service) => !search.trim() || `${service.code} ${service.name}`.toLowerCase().includes(search.trim().toLowerCase())
  );

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 pb-2">
        <CardTitle>{organisation.name} — agreed rates</CardTitle>
        <div className="flex items-center gap-2">
          <Input className="h-9 w-52" placeholder="Search service" value={search}
                 onChange={(event) => setSearch(event.target.value)} />
          <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-ink-muted">
          Leave a service blank to charge the hospital&apos;s own rate. Saving replaces the whole card,
          so a rate removed here stops applying.
        </p>
        {error && <p className="text-sm text-clay">{error}</p>}
        {saved && <p className="text-sm text-pine">{saved}</p>}
        <div className="max-h-96 overflow-y-auto rounded-lg border border-border">
          <table className="w-full min-w-[520px] text-sm">
            <thead className="sticky top-0 bg-mint-card text-left text-xs text-ink-muted">
              <tr>
                <th className="px-3 py-2">Service</th>
                <th className="px-3 py-2 text-right">Our rate</th>
                <th className="px-3 py-2 text-right">Agreed rate (Rs)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {shown.map((service) => (
                <tr key={service.id}>
                  <td className="px-3 py-1.5">
                    <span className="font-mono text-xs text-ink-muted">{service.code}</span> {service.name}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-ink-muted">
                    {formatINR(service.rate_paise)}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    <Input className="ml-auto h-8 w-28 text-right" inputMode="decimal" disabled={!canEdit}
                           value={rates[service.id] ?? ""}
                           onChange={(event) => setRates({ ...rates, [service.id]: event.target.value })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {canEdit && (
          <Button size="sm" disabled={busy} onClick={() => void save()}>
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save {agreed} agreed rates
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
