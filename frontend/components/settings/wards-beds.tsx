"use client";

/**
 * Wards and beds.
 *
 * A ward's daily rate is what an admission is charged each night, so changing
 * it changes tomorrow's charge, not the nights already posted. A bed with a
 * patient in it cannot be taken out of service — the API refuses, and the
 * message says to discharge or transfer first.
 */
import { useCallback, useEffect, useState } from "react";
import { BedDouble, Loader2, Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { BedStatus, WardBoard, WardType } from "@/lib/types/ipd";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import { useModules } from "@/components/dashboard/modules-provider";
import { DEPARTMENT_LABEL } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

const SELECT = "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink";
const WARD_TYPES: WardType[] = [
  "general", "semi_private", "private", "deluxe", "icu", "hdu", "nicu", "labour",
  "post_operative", "day_care",
];
const WARD_TYPE_LABEL: Record<string, string> = {
  general: "General", semi_private: "Semi-private", private: "Private", deluxe: "Deluxe",
  icu: "ICU", hdu: "HDU", nicu: "NICU", labour: "Labour room",
  post_operative: "Post-operative", day_care: "Day care",
};
/** Statuses a person may set. "Occupied" is set by admitting, never by hand. */
const SETTABLE: BedStatus[] = ["vacant", "cleaning", "blocked", "maintenance"];
const BED_STATUS_LABEL: Record<string, string> = {
  vacant: "Free", occupied: "Patient in it", cleaning: "Being cleaned",
  blocked: "Blocked", maintenance: "Under maintenance",
};

interface WardForm {
  code: string;
  existing: boolean;
  name: string;
  ward_type: WardType;
  department: string;
  floor: string;
  daily_rate: string;
  nursing_rate: string;
  is_active: boolean;
}

const EMPTY_WARD: WardForm = {
  code: "", existing: false, name: "", ward_type: "general", department: "", floor: "",
  daily_rate: "", nursing_rate: "0", is_active: true,
};

export function WardsAndBeds({ canEdit }: { canEdit: boolean }) {
  const { departments } = useModules();
  const [wards, setWards] = useState<WardBoard[]>([]);
  const [wardForm, setWardForm] = useState<WardForm | null>(null);
  const [bedFor, setBedFor] = useState<WardBoard | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setWards((await staffApi.wardBoard()).wards);
  }, []);

  useEffect(() => {
    void load().catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [load]);

  const problem =
    wardForm &&
    (!wardForm.code.trim()
      ? "Give the ward a short code."
      : wardForm.name.trim().length < 2
        ? "Give the ward a name."
        : wardForm.daily_rate.trim() === ""
          ? "Enter the nightly rate."
          : null);

  async function saveWard() {
    if (!wardForm || problem) return;
    setBusy(true);
    setError(null);
    try {
      await staffApi.saveWard({
        code: wardForm.code.trim().toUpperCase(),
        name: wardForm.name.trim(),
        ward_type: wardForm.ward_type,
        department: wardForm.department || null,
        floor: wardForm.floor.trim() || null,
        daily_rate_paise: rupeesToPaise(wardForm.daily_rate),
        nursing_rate_paise: rupeesToPaise(wardForm.nursing_rate || "0"),
        is_active: wardForm.is_active,
      });
      setWardForm(null);
      setNotice("Ward saved. Nights already charged keep their old rate.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The ward could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(bedId: string, status: string) {
    setError(null);
    setNotice(null);
    try {
      await staffApi.setBedStatus(bedId, status);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The bed could not be changed.");
    }
  }

  const set = (patch: Partial<WardForm>) => wardForm && setWardForm({ ...wardForm, ...patch });

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-clay">{error}</p>}
      {notice && <p className="text-sm text-pine">{notice}</p>}

      {wardForm && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>{wardForm.existing ? `Edit ${wardForm.name}` : "Add a ward"}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Code</span>
                <Input value={wardForm.code} disabled={wardForm.existing} placeholder="GW"
                       onChange={(event) => set({ code: event.target.value.toUpperCase() })} />
              </label>
              <label className="space-y-1 sm:col-span-2">
                <span className="text-xs text-ink-muted">Name</span>
                <Input value={wardForm.name} onChange={(event) => set({ name: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Kind</span>
                <select className={SELECT} value={wardForm.ward_type}
                        onChange={(event) => set({ ward_type: event.target.value as WardType })}>
                  {WARD_TYPES.map((type) => (
                    <option key={type} value={type}>{WARD_TYPE_LABEL[type]}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Department</span>
                <select className={SELECT} value={wardForm.department}
                        onChange={(event) => set({ department: event.target.value })}>
                  <option value="">Any department</option>
                  {departments.map((dept) => (
                    <option key={dept} value={dept}>{DEPARTMENT_LABEL[dept] ?? dept}</option>
                  ))}
                </select>
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Floor</span>
                <Input value={wardForm.floor} onChange={(event) => set({ floor: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Rate per night (Rs)</span>
                <Input inputMode="decimal" value={wardForm.daily_rate}
                       onChange={(event) => set({ daily_rate: event.target.value })} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-ink-muted">Nursing charge per night (Rs)</span>
                <Input inputMode="decimal" value={wardForm.nursing_rate}
                       onChange={(event) => set({ nursing_rate: event.target.value })} />
              </label>
              <label className="flex items-end gap-2 pb-1.5">
                <input type="checkbox" checked={wardForm.is_active}
                       onChange={(event) => set({ is_active: event.target.checked })} />
                <span>In use</span>
              </label>
            </div>
            {problem && <p className="text-xs text-clay">{problem}</p>}
            <div className="flex gap-2">
              <Button size="sm" disabled={busy || Boolean(problem)} onClick={() => void saveWard()}>
                {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Save ward
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setWardForm(null)}>Cancel</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {bedFor && (
        <AddBed ward={bedFor} onClose={() => setBedFor(null)} onAdded={() => { setBedFor(null); void load(); }} />
      )}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle>Wards</CardTitle>
          {canEdit && !wardForm && (
            <Button size="sm" variant="outline" onClick={() => setWardForm({ ...EMPTY_WARD })}>
              <Plus className="h-4 w-4" /> Add ward
            </Button>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          {wards.length === 0 && <p className="text-sm text-ink-muted">No wards yet.</p>}
          {wards.map((ward) => (
            <div key={ward.id} className="rounded-lg border border-border">
              <div className="flex flex-wrap items-center gap-3 border-b border-border px-3 py-2 text-sm">
                <span className="font-medium">{ward.name}</span>
                <span className="font-mono text-xs text-ink-muted">{ward.code}</span>
                <span className="text-xs text-ink-muted">{WARD_TYPE_LABEL[ward.ward_type] ?? ward.ward_type}</span>
                <span className="text-xs text-ink-muted">
                  {ward.department ? DEPARTMENT_LABEL[ward.department] ?? ward.department : "Any department"}
                </span>
                <span className="text-xs">{formatINR(ward.daily_rate_paise)} per night</span>
                <span className="ml-auto text-xs text-ink-muted">
                  {ward.occupied} of {ward.total_beds} beds occupied
                </span>
                {canEdit && (
                  <>
                    <Button size="sm" variant="ghost" onClick={() => setBedFor(ward)}>
                      <BedDouble className="h-3.5 w-3.5" /> Add bed
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setWardForm({
                      code: ward.code, existing: true, name: ward.name, ward_type: ward.ward_type,
                      department: ward.department ?? "", floor: "",
                      daily_rate: String(ward.daily_rate_paise / 100), nursing_rate: "0", is_active: true,
                    })}>Edit</Button>
                  </>
                )}
              </div>
              <ul className="divide-y divide-border">
                {ward.beds.map((bed) => (
                  <li key={bed.id} className="flex flex-wrap items-center gap-3 px-3 py-1.5 text-sm">
                    <span className="w-16 font-medium">{bed.label}</span>
                    <span className="text-xs text-ink-muted">
                      {BED_STATUS_LABEL[bed.status] ?? bed.status}
                      {bed.occupant ? ` · ${bed.occupant.patient_name}` : ""}
                    </span>
                    {bed.oxygen && <span className="text-xs text-ink-muted">Oxygen</span>}
                    <span className="ml-auto text-xs tabular-nums text-ink-muted">{formatINR(bed.rate_paise)}</span>
                    {canEdit && (
                      <select className="h-8 rounded-md border border-border bg-white px-2 text-xs"
                              value={bed.status} disabled={bed.status === "occupied"}
                              aria-label={`Status of bed ${bed.label}`}
                              onChange={(event) => void setStatus(bed.id, event.target.value)}>
                        {bed.status === "occupied" && <option value="occupied">Patient in it</option>}
                        {SETTABLE.map((status) => (
                          <option key={status} value={status}>{BED_STATUS_LABEL[status]}</option>
                        ))}
                      </select>
                    )}
                  </li>
                ))}
                {ward.beds.length === 0 && (
                  <li className="px-3 py-2 text-xs text-ink-muted">No beds in this ward yet.</li>
                )}
              </ul>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function AddBed({
  ward, onClose, onAdded,
}: { ward: WardBoard; onClose: () => void; onAdded: () => void }) {
  const [label, setLabel] = useState("");
  const [rate, setRate] = useState("");
  const [oxygen, setOxygen] = useState(false);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add() {
    setBusy(true);
    setError(null);
    try {
      await staffApi.addBed({
        ward_id: ward.id,
        label: label.trim(),
        rate_override_paise: rate.trim() ? rupeesToPaise(rate) : null,
        is_oxygen_supported: oxygen,
        notes: notes.trim() || null,
      });
      onAdded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The bed could not be added.");
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle>Add a bed to {ward.name}</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="space-y-1">
            <span className="text-xs text-ink-muted">Bed number or label</span>
            <Input value={label} autoFocus onChange={(event) => setLabel(event.target.value)} />
          </label>
          <label className="space-y-1">
            <span className="text-xs text-ink-muted">Rate for this bed (Rs, optional)</span>
            <Input inputMode="decimal" value={rate} placeholder={String(ward.daily_rate_paise / 100)}
                   onChange={(event) => setRate(event.target.value)} />
          </label>
          <label className="space-y-1 sm:col-span-2">
            <span className="text-xs text-ink-muted">Notes</span>
            <Input value={notes} onChange={(event) => setNotes(event.target.value)} />
          </label>
          <label className="flex items-end gap-2 pb-1.5">
            <input type="checkbox" checked={oxygen} onChange={(event) => setOxygen(event.target.checked)} />
            <span>Oxygen point</span>
          </label>
        </div>
        {error && <p className="text-xs text-clay">{error}</p>}
        <div className="flex gap-2">
          <Button size="sm" disabled={busy || label.trim() === ""} onClick={() => void add()}>
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Add bed
          </Button>
          <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
        </div>
      </CardContent>
    </Card>
  );
}
