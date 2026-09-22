"use client";

/**
 * The consultant register.
 *
 * Kept by management and admin. A consultant is not a login: visiting doctors
 * have no account, so linking one is optional. Nobody is deleted — a doctor who
 * has left is marked as not in use, drops out of the pickers, and stays on the
 * records they signed. Their payout share is set on the Accounts screen, where
 * the change is audited, and is only shown here.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { Loader2, Pencil, Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { Consultant } from "@/lib/types/appointments";
import type { ServiceItem } from "@/lib/types/emr";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import type { Department, User } from "@/lib/types/core";
import { DEPARTMENT_LABEL } from "@/lib/format";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SELECT = "h-9 rounded-md border border-border bg-white px-2 text-sm text-ink";
const DEPARTMENTS: Department[] = ["orthopedics", "gynecology"];
const DAYS: [string, string][] = [["1", "Mon"], ["2", "Tue"], ["3", "Wed"], ["4", "Thu"], ["5", "Fri"], ["6", "Sat"], ["7", "Sun"]];

interface ConsultantForm {
  id?: string;
  full_name: string;
  department: Department;
  sex: string;
  qualification: string;
  registration_number: string;
  phone_number: string;
  user_id: string;
  appointment_minutes: string;
  first_consultation_free: boolean;
  opd_start_time: string;
  opd_end_time: string;
  opd_days: string[];
  free_follow_up_days: string;
  consultation_service_code: string;
  notes: string;
  display_in_opd: boolean;
  display_in_ipd: boolean;
  display_in_diagnostics: boolean;
  sort_order: string;
  is_primary: boolean;
  is_active: boolean;
}

const EMPTY: ConsultantForm = {
  full_name: "", department: "orthopedics", sex: "", qualification: "", registration_number: "", phone_number: "",
  user_id: "", appointment_minutes: "15", first_consultation_free: false, opd_start_time: "09:00",
  opd_end_time: "17:00", opd_days: ["1", "2", "3", "4", "5", "6"], free_follow_up_days: "0",
  consultation_service_code: "", notes: "",
  display_in_opd: true, display_in_ipd: true, display_in_diagnostics: true,
  sort_order: "0", is_primary: false, is_active: true,
};

function toForm(c: Consultant): ConsultantForm {
  return {
    id: c.id, full_name: c.full_name, department: c.department, sex: c.sex ?? "",
    qualification: c.qualification ?? "",
    registration_number: c.registration_number ?? "", phone_number: c.phone_number ?? "", user_id: c.user_id ?? "",
    appointment_minutes: String(c.appointment_minutes), first_consultation_free: Boolean(c.first_consultation_free),
    opd_start_time: c.opd_start_time.slice(0, 5), opd_end_time: c.opd_end_time.slice(0, 5),
    opd_days: c.opd_days.split(",").filter(Boolean), free_follow_up_days: String(c.free_follow_up_days),
    consultation_service_code: c.consultation_service_code ?? "", notes: c.notes ?? "",
    display_in_opd: c.display_in_opd, display_in_ipd: c.display_in_ipd,
    display_in_diagnostics: c.display_in_diagnostics,
    sort_order: String(c.sort_order), is_primary: c.is_primary, is_active: c.is_active,
  };
}

function days(value: string): string {
  const picked = value.split(",");
  return DAYS.filter(([n]) => picked.includes(n)).map(([, label]) => label).join(" ");
}

export function ConsultantsAdmin() {
  const { user } = useAuth();
  const editable = ["admin", "manager"].includes(user?.role ?? "");
  const [consultants, setConsultants] = useState<Consultant[]>([]);
  const [services, setServices] = useState<ServiceItem[] | null>(null);
  const [logins, setLogins] = useState<User[] | null>(null);
  const [form, setForm] = useState<ConsultantForm | null>(null);
  const [rateCardFor, setRateCardFor] = useState<Consultant | null>(null);
  const [search, setSearch] = useState("");
  const [showRetired, setShowRetired] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setConsultants(await staffApi.consultants({ active_only: false }));
  }, []);

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : String(err)));
    // Both optional: the price list and staff logins are not every editor's to read.
    staffApi.serviceItems().then(setServices).catch(() => setServices(null));
    if (user?.role === "admin") staffApi.staffUsers().then(setLogins).catch(() => setLogins(null));
  }, [load, user?.role]);

  const shown = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return consultants.filter((c) => (showRetired || c.is_active)
      && (!needle || `${c.full_name} ${c.qualification ?? ""} ${c.registration_number ?? ""}`.toLowerCase().includes(needle)));
  }, [consultants, search, showRetired]);

  const loginName = (id?: string | null) => logins?.find((u) => u.id === id)?.full_name;
  const consultationServices = services?.filter((s) => s.category === "consultation" && s.is_active) ?? null;

  const problem = form && (
    form.full_name.trim().length < 2 ? "Enter the consultant's name."
      : form.opd_days.length === 0 ? "Pick at least one OPD day."
      : form.opd_end_time <= form.opd_start_time ? "OPD hours must end after they start."
      : null
  );

  async function save() {
    if (!form || problem) return;
    setBusy(true);
    setError(null);
    try {
      await staffApi.saveConsultant({
        full_name: form.full_name.trim(), department: form.department,
        sex: form.sex || null,
        qualification: form.qualification.trim() || null, registration_number: form.registration_number.trim() || null,
        phone_number: form.phone_number.trim() || null, user_id: form.user_id || null,
        appointment_minutes: Number(form.appointment_minutes) || 15,
        first_consultation_free: form.first_consultation_free,
        opd_start_time: form.opd_start_time, opd_end_time: form.opd_end_time,
        opd_days: [...form.opd_days].sort().join(","),
        free_follow_up_days: Number(form.free_follow_up_days) || 0,
        consultation_service_code: form.consultation_service_code.trim() || null,
        notes: form.notes.trim() || null,
        display_in_opd: form.display_in_opd, display_in_ipd: form.display_in_ipd,
        display_in_diagnostics: form.display_in_diagnostics,
        sort_order: Number(form.sort_order) || 0, is_primary: form.is_primary,
        is_active: form.is_active,
      }, form.id);
      setForm(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The consultant could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  const set = (patch: Partial<ConsultantForm>) => form && setForm({ ...form, ...patch });

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-clay">{error}</p>}

      {form && (
        <Card>
          <CardHeader className="pb-2"><CardTitle>{form.id ? `Edit ${form.full_name}` : "Add a consultant"}</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Name</span>
                <Input value={form.full_name} placeholder="Dr. ..." onChange={(e) => set({ full_name: e.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Department</span>
                <select className={`${SELECT} w-full`} value={form.department}
                        onChange={(e) => set({ department: e.target.value as Department })}>
                  {DEPARTMENTS.map((d) => <option key={d} value={d}>{DEPARTMENT_LABEL[d] ?? d}</option>)}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Sex</span>
                <select className={`${SELECT} w-full`} value={form.sex}
                        onChange={(e) => set({ sex: e.target.value })}>
                  <option value="">Not recorded</option>
                  <option value="female">Female</option>
                  <option value="male">Male</option>
                  <option value="other">Other</option>
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Phone</span>
                <Input value={form.phone_number} inputMode="tel" onChange={(e) => set({ phone_number: e.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Qualification (printed under the signature)</span>
                <Input value={form.qualification} placeholder="MBBS, MS (Ortho)" onChange={(e) => set({ qualification: e.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Medical registration number</span>
                <Input value={form.registration_number} onChange={(e) => set({ registration_number: e.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Consultation fee (price list code)</span>
                {consultationServices ? (
                  <select className={`${SELECT} w-full`} value={form.consultation_service_code}
                          onChange={(e) => set({ consultation_service_code: e.target.value })}>
                    <option value="">Department&apos;s standard rate</option>
                    {consultationServices.map((s) => (
                      <option key={s.code} value={s.code}>{s.code} — {s.name}</option>
                    ))}
                    {form.consultation_service_code && !consultationServices.some((s) => s.code === form.consultation_service_code) && (
                      <option value={form.consultation_service_code}>{form.consultation_service_code} (not on the price list)</option>
                    )}
                  </select>
                ) : (
                  <Input value={form.consultation_service_code} placeholder="e.g. OPD-ORTHO-NEW"
                         onChange={(e) => set({ consultation_service_code: e.target.value.toUpperCase() })} />
                )}
              </label>
            </div>

            <div className="space-y-1">
              <span className="text-xs text-ink-muted">OPD days</span>
              <div className="flex flex-wrap gap-3">
                {DAYS.map(([n, label]) => (
                  <label key={n} className="flex items-center gap-1.5">
                    <input type="checkbox" checked={form.opd_days.includes(n)}
                           onChange={(e) => set({ opd_days: e.target.checked ? [...form.opd_days, n] : form.opd_days.filter((d) => d !== n) })} />
                    {label}
                  </label>
                ))}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">OPD from</span>
                <Input type="time" value={form.opd_start_time} onChange={(e) => set({ opd_start_time: e.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">OPD until</span>
                <Input type="time" value={form.opd_end_time} onChange={(e) => set({ opd_end_time: e.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Minutes per appointment (5-120)</span>
                <Input type="number" min={5} max={120} value={form.appointment_minutes}
                       onChange={(e) => set({ appointment_minutes: e.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Free follow-up within (days, 0 = never)</span>
                <Input type="number" min={0} max={365} value={form.free_follow_up_days}
                       onChange={(e) => set({ free_follow_up_days: e.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Sort order (lower shows first)</span>
                <Input type="number" min={0} max={999} value={form.sort_order}
                       onChange={(e) => set({ sort_order: e.target.value })} />
              </label>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {logins ? (
                <label className="space-y-1">
                  <span className="text-xs text-ink-muted">Their login (optional)</span>
                  <select className={`${SELECT} w-full`} value={form.user_id} onChange={(e) => set({ user_id: e.target.value })}>
                    <option value="">No login — visiting or does not use the system</option>
                    {logins.filter((u) => u.role === "doctor" || u.id === form.user_id).map((u) => (
                      <option key={u.id} value={u.id}>{u.full_name} ({u.email})</option>
                    ))}
                  </select>
                </label>
              ) : (
                <p className="self-end text-xs text-ink-muted">
                  {form.user_id ? "Linked to a login. " : "No login linked. "}Only an admin can change the linked login.
                </p>
              )}
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Notes</span>
                <Input value={form.notes} onChange={(e) => set({ notes: e.target.value })} />
              </label>
            </div>

            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.first_consultation_free}
                       onChange={(e) => set({ first_consultation_free: e.target.checked })} />
                First consultation free
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.is_primary}
                       onChange={(e) => set({ is_primary: e.target.checked })} />
                Department&apos;s primary consultant
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.is_active} onChange={(e) => set({ is_active: e.target.checked })} />
                In use (shown in the pickers)
              </label>
            </div>
            <div className="space-y-1">
              <span className="text-xs text-ink-muted">Shown as a consultant option on</span>
              <div className="flex flex-wrap items-center gap-4">
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={form.display_in_opd}
                         onChange={(e) => set({ display_in_opd: e.target.checked })} />
                  OPD registration
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={form.display_in_ipd}
                         onChange={(e) => set({ display_in_ipd: e.target.checked })} />
                  IPD admission
                </label>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={form.display_in_diagnostics}
                         onChange={(e) => set({ display_in_diagnostics: e.target.checked })} />
                  Diagnostics
                </label>
              </div>
            </div>
            <p className="text-xs text-ink-muted">The payout share is set on the Accounts screen, not here.</p>

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
          <CardTitle>Consultants</CardTitle>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <Input className="h-9 w-56" placeholder="Search name or registration" value={search}
                   onChange={(e) => setSearch(e.target.value)} />
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={showRetired} onChange={(e) => setShowRetired(e.target.checked)} />
              Show not in use
            </label>
            {editable && !form && (
              <Button size="sm" variant="outline" onClick={() => setForm({ ...EMPTY })}>
                <Plus className="h-4 w-4" /> Add consultant
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {shown.length === 0 ? (
            <p className="text-sm text-ink-muted">No consultants match.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-sm">
                <thead className="text-left text-xs text-ink-muted">
                  <tr>
                    <th className="py-2 pr-3">Consultant</th>
                    <th className="py-2 pr-3">Department</th>
                    <th className="py-2 pr-3">OPD</th>
                    <th className="py-2 pr-3">Slot</th>
                    <th className="py-2 pr-3">Free follow-up</th>
                    <th className="py-2 pr-3">Fee code</th>
                    <th className="py-2 pr-3">Payout</th>
                    <th className="py-2" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {shown.map((c) => (
                    <tr key={c.id} className={c.is_active ? "" : "text-ink-muted"}>
                      <td className="py-2 pr-3">
                        <span className="font-medium">{c.full_name}</span>
                        {c.is_primary && <Badge className="ml-2">Primary</Badge>}
                        {!c.is_active && <Badge variant="outline" className="ml-2">Not in use</Badge>}
                        <span className="block text-xs text-ink-muted">
                          {[c.sex && c.sex[0].toUpperCase() + c.sex.slice(1),
                            c.qualification, c.registration_number && `Reg. ${c.registration_number}`,
                            c.user_id && (loginName(c.user_id) ? `Login: ${loginName(c.user_id)}` : "Has a login")]
                            .filter(Boolean).join(" · ") || "—"}
                        </span>
                      </td>
                      <td className="py-2 pr-3">{DEPARTMENT_LABEL[c.department] ?? c.department}</td>
                      <td className="py-2 pr-3">
                        {days(c.opd_days)}
                        <span className="block text-xs text-ink-muted">{c.opd_start_time.slice(0, 5)}–{c.opd_end_time.slice(0, 5)}</span>
                      </td>
                      <td className="py-2 pr-3">{c.appointment_minutes} min</td>
                      <td className="py-2 pr-3">
                        {c.free_follow_up_days ? `${c.free_follow_up_days} days` : "None"}
                        {c.first_consultation_free && <span className="block text-xs text-ink-muted">First visit free</span>}
                      </td>
                      <td className="py-2 pr-3 font-mono text-xs">{c.consultation_service_code || "Standard"}</td>
                      <td className="py-2 pr-3">{c.payout_share_percent}%</td>
                      <td className="py-2 text-right">
                        <Button size="sm" variant="ghost" onClick={() => setRateCardFor(c)}>Rates</Button>
                        {editable && (
                          <Button size="sm" variant="ghost" aria-label={`Edit ${c.full_name}`} onClick={() => setForm(toForm(c))}>
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
        <ConsultantRateCard consultant={rateCardFor} canEdit={editable} onClose={() => setRateCardFor(null)} />
      )}
    </div>
  );
}

function ConsultantRateCard({
  consultant, canEdit, onClose,
}: { consultant: Consultant; canEdit: boolean; onClose: () => void }) {
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [rates, setRates] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setSaved(null);
    Promise.all([staffApi.serviceItems(true), staffApi.consultantRates(consultant.id)])
      .then(([list, agreed]) => {
        if (!live) return;
        setServices(list);
        setRates(Object.fromEntries(agreed.map((rate) => [rate.service_item_id, String(rate.rate_paise / 100)])));
      })
      .catch((err) => live && setError(err instanceof Error ? err.message : "The rate card could not be loaded."));
    return () => { live = false; };
  }, [consultant.id]);

  const agreed = Object.values(rates).filter((value) => value.trim() !== "").length;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const card = Object.entries(rates)
        .filter(([, value]) => value.trim() !== "")
        .map(([service_item_id, value]) => ({ service_item_id, rate_paise: rupeesToPaise(value) }));
      await staffApi.saveConsultantRates(consultant.id, card);
      setSaved(`${card.length} ${card.length === 1 ? "rate" : "rates"} saved.`);
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
        <CardTitle>{consultant.full_name} — own rates</CardTitle>
        <div className="flex items-center gap-2">
          <Input className="h-9 w-52" placeholder="Search service" value={search}
                 onChange={(event) => setSearch(event.target.value)} />
          <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-ink-muted">
          Leave a service blank to charge the hospital&apos;s own rate. Beats an organisation&apos;s blanket
          discount, but a negotiated rate for the patient&apos;s payer still wins over this. Saving replaces
          the whole card.
        </p>
        {error && <p className="text-sm text-clay">{error}</p>}
        {saved && <p className="text-sm text-pine">{saved}</p>}
        <div className="max-h-96 overflow-y-auto rounded-lg border border-border">
          <table className="w-full min-w-[520px] text-sm">
            <thead className="sticky top-0 bg-mint-card text-left text-xs text-ink-muted">
              <tr>
                <th className="px-3 py-2">Service</th>
                <th className="px-3 py-2 text-right">Our rate</th>
                <th className="px-3 py-2 text-right">Their rate (Rs)</th>
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
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save {agreed} rates
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
