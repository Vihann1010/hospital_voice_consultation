"use client";

/**
 * The ward panel: bed board, admission, bedside actions, discharge.
 *
 * Built around what actually happens on a ward. A vacant bed is a place to
 * admit someone; an occupied bed is a patient with charges accruing and a
 * discharge coming. So the bed is the object you tap, and everything else
 * hangs off it — there is no separate "admissions" page to navigate to,
 * because the incharge is always looking at the board anyway.
 *
 * Discharge is deliberately two steps, bill then summary, because they are
 * two different decisions: the family settles at the counter, and the doctor
 * signs the summary. Collapsing them into one button would let a patient walk
 * out with an unsigned summary or an unpaid bill.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle, ArrowRight, BedDouble, Check, Droplet, FileText, IndianRupee,
  Loader2, LogOut, Plus, Printer, Search, Stethoscope, UserPlus, X,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { BedCell, Census, DeterioratingPatient, WardBoard } from "@/lib/types/ipd";
import { BED_STATUS_STYLE, NEWS_BANDS, WARD_TYPE_LABEL, dayOfStay } from "@/lib/types/ipd";
import { formatINR, rupeesToPaise } from "@/lib/types/emr";
import type { PaymentMode } from "@/lib/types/emr";
import { PaymentModeFields } from "@/components/finance/payment-mode-fields";
import { ADVANCE_MODES, TakeAdvance, openWalletReceipt } from "@/components/ipd/take-advance";
import type { Department, Gender } from "@/lib/types/core";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const REFRESH_MS = 30000;

interface FoundPatient {
  id: string;
  uhid: string | null;
  name: string;
  age: number;
  gender: string;
  phone_number: string;
  blood_group?: string | null;
}

type Sheet =
  | { kind: "admit"; bed: BedCell; ward: WardBoard }
  | { kind: "bed"; bed: BedCell; ward: WardBoard }
  | null;

// --------------------------------------------------------------- admit sheet
function AdmitSheet({
  bed, ward, onDone, onClose,
}: {
  bed: BedCell;
  ward: WardBoard;
  onDone: () => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<FoundPatient[] | null>(null);
  const [chosen, setChosen] = useState<FoundPatient | null>(null);
  const [creating, setCreating] = useState(false);

  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState<Gender>("male");
  const [phone, setPhone] = useState("");
  const [bloodGroup, setBloodGroup] = useState("");

  const [diagnosis, setDiagnosis] = useState("");
  const [reason, setReason] = useState("");
  const [doctor, setDoctor] = useState("");
  const [department, setDepartment] = useState<Department>(
    (ward.department as Department) ?? "orthopedics"
  );
  const [advance, setAdvance] = useState("");
  const [attendantName, setAttendantName] = useState("");
  const [attendantPhone, setAttendantPhone] = useState("");
  const [allergies, setAllergies] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (query.trim().length < 2) {
      setResults(null);
      return;
    }
    const timer = setTimeout(() => {
      staffApi
        .searchPatientsForAdmission(query.trim())
        .then(setResults)
        .catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  const [advanceMode, setAdvanceMode] = useState<PaymentMode>("cash");
  const [advanceDetails, setAdvanceDetails] = useState<Record<string, string>>({});

  const ready =
    (chosen !== null || (name.trim() && age && phone.trim().length >= 10)) &&
    doctor.trim().length > 0;

  async function admit() {
    setBusy(true);
    setError(null);
    try {
      let patientId = chosen?.id;
      if (!patientId) {
        // Registered through the same allocator reception uses, so a ward
        // admission gets a real UHID rather than a second numbering scheme.
        const created = await staffApi.registerPatientForAdmission({
          name: name.trim(),
          age: Number(age),
          gender,
          phone_number: phone.trim(),
          blood_group: bloodGroup.trim() || null,
        });
        patientId = created.id;
      }
      const admitted = await staffApi.admitPatient({
        patient_id: patientId,
        bed_id: bed.id,
        department,
        admitting_doctor_name: doctor.trim(),
        provisional_diagnosis: diagnosis.trim() || null,
        reason_for_admission: reason.trim() || null,
        advance_paid_paise: rupeesToPaise(advance || "0"),
        advance_mode: advanceMode,
        advance_mode_details: Object.keys(advanceDetails).length ? advanceDetails : null,
        attendant_name: attendantName.trim() || null,
        attendant_phone: attendantPhone.trim() || null,
        allergies: allergies
          .split(",")
          .map((a) => a.trim())
          .filter(Boolean),
      });
      toast.success("Admitted", `${chosen?.name ?? name} to ${bed.label}`);
      // The advance is a receipted collection; the family takes the receipt.
      const receiptId = admitted.advance_receipt_entry_id as string | null | undefined;
      if (receiptId) {
        toast.success("Advance receipted", String(admitted.advance_receipt_number ?? ""));
        void openWalletReceipt(receiptId);
      }
      onDone();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not admit.";
      setError(message);
      toast.error("Admission failed", message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <BedDouble className="h-4 w-4 text-pine" />
        <h3 className="font-display font-semibold text-pine">
          Admit to {bed.label}
        </h3>
        <span className="ml-auto text-xs text-ink-muted">
          {ward.name} · {formatINR(bed.rate_paise)}/day
        </span>
      </div>

      {/* Who */}
      {chosen ? (
        <div className="flex items-center gap-3 rounded-lg bg-mint px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-pine">{chosen.name}</p>
            <p className="text-xs text-ink-muted">
              {chosen.uhid} · {chosen.age} yrs · {chosen.gender}
              {chosen.blood_group ? ` · ${chosen.blood_group}` : ""}
            </p>
          </div>
          <button onClick={() => setChosen(null)} aria-label="Choose someone else"
                  className="rounded p-1 text-ink-faint hover:text-clay">
            <X className="h-4 w-4" />
          </button>
        </div>
      ) : creating ? (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="field-label" htmlFor="ad-name">Full name</label>
              <Input id="ad-name" value={name} autoFocus
                     onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <label className="field-label" htmlFor="ad-phone">Mobile</label>
              <Input id="ad-phone" value={phone} inputMode="numeric"
                     onChange={(e) => setPhone(e.target.value)} />
            </div>
            <div>
              <label className="field-label" htmlFor="ad-age">Age</label>
              <Input id="ad-age" value={age} inputMode="numeric"
                     onChange={(e) => setAge(e.target.value)} />
            </div>
            <div>
              <label className="field-label" htmlFor="ad-gender">Gender</label>
              <select id="ad-gender" value={gender} className="field-input"
                      onChange={(e) => setGender(e.target.value as Gender)}>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>
          <div>
            <label className="field-label" htmlFor="ad-blood">Blood group</label>
            <Input id="ad-blood" value={bloodGroup} placeholder="e.g. B+"
                   onChange={(e) => setBloodGroup(e.target.value)} />
          </div>
          <Button variant="ghost" size="sm" onClick={() => setCreating(false)}>
            Search for an existing patient instead
          </Button>
        </div>
      ) : (
        <>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-faint" />
            <Input value={query} autoFocus className="pl-9"
                   placeholder="UHID, mobile or name"
                   onChange={(e) => setQuery(e.target.value)} />
          </div>
          {results !== null && (
            results.length === 0 ? (
              <p className="text-sm text-ink-muted">
                No match. Register this patient as new.
              </p>
            ) : (
              <ul className="divide-y divide-border rounded-lg border border-border">
                {results.map((p) => (
                  <li key={p.id}>
                    <button onClick={() => { setChosen(p); setResults(null); setQuery(""); }}
                            className="w-full px-4 py-2.5 text-left transition hover:bg-mint">
                      <p className="text-sm font-medium text-ink">{p.name}</p>
                      <p className="text-xs text-ink-faint">
                        {p.uhid} · {p.age} yrs · {p.phone_number}
                      </p>
                    </button>
                  </li>
                ))}
              </ul>
            )
          )}
          <Button variant="outline" size="sm" onClick={() => setCreating(true)}>
            <UserPlus /> Register new patient
          </Button>
        </>
      )}

      {/* Admission details */}
      <div className="grid gap-3 border-t border-border pt-4 sm:grid-cols-2">
        <div>
          <label className="field-label" htmlFor="ad-dept">Department</label>
          <select id="ad-dept" value={department} className="field-input"
                  onChange={(e) => setDepartment(e.target.value as Department)}>
            <option value="orthopedics">Trauma &amp; Orthopedics</option>
            <option value="gynecology">Maternity &amp; Gynecology</option>
          </select>
        </div>
        <div>
          <label className="field-label" htmlFor="ad-doc">Under doctor</label>
          <Input id="ad-doc" value={doctor} placeholder="Dr A K Agarwal"
                 onChange={(e) => setDoctor(e.target.value)} />
        </div>
      </div>
      <div>
        <label className="field-label" htmlFor="ad-diag">Provisional diagnosis</label>
        <Input id="ad-diag" value={diagnosis}
               onChange={(e) => setDiagnosis(e.target.value)} />
      </div>
      <div>
        <label className="field-label" htmlFor="ad-reason">Reason for admission</label>
        <Input id="ad-reason" value={reason}
               onChange={(e) => setReason(e.target.value)} />
      </div>
      <div>
        {/* Carried onto the chart so it is at the bedside without a lookup. */}
        <label className="field-label" htmlFor="ad-allergy">
          Allergies (comma separated)
        </label>
        <Input id="ad-allergy" value={allergies} placeholder="Penicillin, sulpha"
               onChange={(e) => setAllergies(e.target.value)} />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label className="field-label" htmlFor="ad-adv">Advance (₹), receipted</label>
          <div className="flex gap-2">
            <Input id="ad-adv" value={advance} inputMode="decimal" placeholder="0"
                   onChange={(e) => setAdvance(e.target.value)} />
            <select aria-label="Advance paid by" value={advanceMode} className="field-input w-28"
                    onChange={(e) => { setAdvanceMode(e.target.value as PaymentMode); setAdvanceDetails({}); }}>
              {ADVANCE_MODES.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          <label className="field-label" htmlFor="ad-att">Attendant</label>
          <Input id="ad-att" value={attendantName}
                 onChange={(e) => setAttendantName(e.target.value)} />
        </div>
        <div>
          <label className="field-label" htmlFor="ad-attp">Attendant mobile</label>
          <Input id="ad-attp" value={attendantPhone} inputMode="numeric"
                 onChange={(e) => setAttendantPhone(e.target.value)} />
        </div>
      </div>

      {rupeesToPaise(advance || "0") > 0 && (
        <PaymentModeFields mode={advanceMode} values={advanceDetails} onChange={setAdvanceDetails} />
      )}

      {error && (
        <p role="alert" className="rounded-md bg-clay/10 px-3 py-2 text-xs text-clay">
          {error}
        </p>
      )}

      <div className="flex gap-2">
        <Button variant="outline" className="flex-1" onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button className="flex-1" onClick={admit} disabled={!ready || busy}>
          {busy ? <Loader2 className="animate-spin" /> : <Check />} Admit
        </Button>
      </div>
    </div>
  );
}

// ----------------------------------------------------------- bedside sheet
function BedSheet({
  bed, ward, onChanged, onClose,
}: {
  bed: BedCell;
  ward: WardBoard;
  onChanged: () => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const occupant = bed.occupant!;
  const [bill, setBill] = useState<Record<string, any> | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"charges" | "discharge">("charges");

  // charge entry
  const [category, setCategory] = useState("procedure");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [quantity, setQuantity] = useState("1");

  // discharge
  const [invoice, setInvoice] = useState<Record<string, any> | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [finalDiagnosis, setFinalDiagnosis] = useState("");

  const loadBill = useCallback(async () => {
    try {
      setBill(await staffApi.runningBill(occupant.admission_id));
    } catch {
      setBill(null);
    }
  }, [occupant.admission_id]);

  useEffect(() => { void loadBill(); }, [loadBill]);

  async function addCharge() {
    if (!description.trim() || !amount) return;
    setBusy(true);
    try {
      await staffApi.postAdmissionCharge(occupant.admission_id, {
        category,
        description: description.trim(),
        unit_rate_paise: rupeesToPaise(amount),
        quantity: Math.max(1, Number(quantity) || 1),
      });
      setDescription(""); setAmount(""); setQuantity("1");
      await loadBill();
      toast.success("Charge added");
    } catch (err) {
      toast.error("Could not add the charge",
        err instanceof Error ? err.message : undefined);
    } finally {
      setBusy(false);
    }
  }

  async function raiseInvoice() {
    setBusy(true);
    try {
      const result = await staffApi.raiseIpdInvoice(occupant.admission_id);
      setInvoice(result.invoice);
      toast.success("Bill raised", result.invoice.invoice_number);
    } catch (err) {
      toast.error("Could not raise the bill",
        err instanceof Error ? err.message : undefined);
    } finally {
      setBusy(false);
    }
  }

  async function draftSummary() {
    setBusy(true);
    try {
      const result = await staffApi.draftDischargeSummary(occupant.admission_id);
      setSummary(result.content);
      toast.success("Draft ready", "A doctor must review and sign it.");
    } catch (err) {
      toast.error("Could not draft the summary",
        err instanceof Error ? err.message : undefined);
    } finally {
      setBusy(false);
    }
  }

  async function completeDischarge() {
    setBusy(true);
    try {
      await staffApi.dischargePatient(occupant.admission_id, {
        discharge_type: "routine",
        final_diagnosis: finalDiagnosis.trim() || null,
      });
      toast.success("Discharged", `${bed.label} is now free to clean`);
      onChanged();
    } catch (err) {
      toast.error("Could not discharge",
        err instanceof Error ? err.message : undefined);
    } finally {
      setBusy(false);
    }
  }

  const balance = bill ? bill.balance_paise : 0;

  return (
    <div className="space-y-4">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-lg font-semibold text-pine">
            {occupant.patient_name}
          </h3>
          <p className="text-sm text-ink-muted">
            {occupant.uhid} · {occupant.age} yrs · {occupant.gender}
          </p>
          <p className="text-xs text-ink-faint">
            {occupant.ip_number} · {ward.name} {bed.label} · Day{" "}
            {dayOfStay(occupant.admitted_at)} · {occupant.doctor}
          </p>
          {occupant.on_leave && (
            <p className="mt-1 text-sm font-medium text-marigold-deep">
              On leave{occupant.expected_return_on ? ` · expected back ${occupant.expected_return_on}` : ""}
            </p>
          )}
          <p className="mt-1 text-sm text-ink-muted">
            Diet: {occupant.diet ? <span className="font-medium text-ink">{occupant.diet}</span>
              : <span className="font-medium text-clay">none ordered</span>}
          </p>
          {occupant.diagnosis && (
            <p className="mt-1 text-sm text-ink">{occupant.diagnosis}</p>
          )}
          {/* Notes, observations and the discharge summary live on the case
              sheet. This panel stays the quick bedside view. */}
          <Link
            href={`/ward/admissions/${occupant.admission_id}`}
            className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-pine hover:underline"
          >
            Open case sheet <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
        <button onClick={onClose} aria-label="Close"
                className="rounded p-1 text-ink-faint hover:text-clay">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex gap-1 rounded-lg bg-mint p-1">
        {(["charges", "discharge"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
                  className={cn(
                    "flex-1 rounded-md px-3 py-1.5 text-sm font-medium capitalize transition",
                    tab === t ? "bg-white text-pine shadow-sm" : "text-ink-muted"
                  )}>
            {t}
          </button>
        ))}
      </div>

      {tab === "charges" && (
        <div className="space-y-3">
          {bill && (
            <div className="rounded-xl bg-mint p-4">
              <div className="space-y-1 text-sm">
                {Object.entries(bill.by_category as Record<string, any>).map(
                  ([key, value]) => (
                    <div key={key} className="flex justify-between">
                      <span className="capitalize text-ink-muted">
                        {key.replace("_", " ")} × {value.count}
                      </span>
                      <span className="tabular text-ink">
                        {formatINR(value.total_paise)}
                      </span>
                    </div>
                  )
                )}
              </div>
              <div className="mt-2 flex justify-between border-t border-pine/10 pt-2">
                <span className="font-medium text-pine">Total so far</span>
                <span className="tabular font-display font-semibold text-pine">
                  {formatINR(bill.total_paise)}
                </span>
              </div>
              <div className="flex justify-between text-xs text-ink-muted">
                <span>Advance held</span>
                <span className="tabular">{formatINR(bill.advance_paid_paise)}</span>
              </div>
              <div className="flex justify-between text-sm font-medium">
                <span className={balance > 0 ? "text-clay" : "text-pine"}>Balance</span>
                <span className={cn("tabular", balance > 0 ? "text-clay" : "text-pine")}>
                  {formatINR(balance)}
                </span>
              </div>
            </div>
          )}

          <TakeAdvance
            admissionId={occupant.admission_id}
            onDone={() => void staffApi.runningBill(occupant.admission_id).then(setBill).catch(() => undefined)}
          />

          <div className="space-y-2 rounded-xl border border-border p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              Add a charge
            </p>
            <select value={category} className="field-input"
                    onChange={(e) => setCategory(e.target.value)}>
              <option value="procedure">Procedure</option>
              <option value="investigation">Investigation</option>
              <option value="medicine">Medicine</option>
              <option value="consumable">Consumable</option>
              <option value="doctor_visit">Doctor visit</option>
              <option value="oxygen">Oxygen</option>
              <option value="other">Other</option>
            </select>
            <Input value={description} placeholder="Description"
                   onChange={(e) => setDescription(e.target.value)} />
            <div className="flex gap-2">
              <Input value={amount} inputMode="decimal" placeholder="Rate ₹"
                     onChange={(e) => setAmount(e.target.value)} />
              <Input value={quantity} inputMode="numeric" className="w-20"
                     onChange={(e) => setQuantity(e.target.value)} />
              <Button onClick={addCharge} disabled={busy || !description || !amount}>
                {busy ? <Loader2 className="animate-spin" /> : <Plus />}
              </Button>
            </div>
          </div>
        </div>
      )}

      {tab === "discharge" && (
        <div className="space-y-3">
          {/* Two steps on purpose: the family settles the bill at the counter,
              and a doctor signs the summary. One button would let a patient
              leave with neither done. */}
          <div className="rounded-xl border border-border p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              1 · Final bill
            </p>
            {invoice ? (
              <div className="mt-2">
                <p className="text-sm text-ink">{invoice.invoice_number}</p>
                <p className="tabular font-display text-xl font-semibold text-pine">
                  {formatINR(invoice.total_paise)}
                </p>
                <p className="text-xs text-ink-muted">
                  Paid {formatINR(invoice.paid_paise)} · Balance{" "}
                  {formatINR(invoice.total_paise - invoice.paid_paise)}
                </p>
                {invoice.total_paise - invoice.paid_paise > 0 && (
                  <p className="mt-2 flex items-start gap-1.5 rounded-md bg-marigold/10 px-2.5 py-2 text-xs text-marigold-deep">
                    <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    Balance outstanding — settle at the counter before the patient
                    leaves.
                  </p>
                )}
                <Button variant="outline" size="sm" className="mt-2"
                        onClick={() => window.print()}>
                  <Printer /> Print bill
                </Button>
              </div>
            ) : (
              <Button className="mt-2 w-full" size="sm" onClick={raiseInvoice}
                      disabled={busy}>
                {busy ? <Loader2 className="animate-spin" /> : <IndianRupee />}
                Raise final bill
              </Button>
            )}
          </div>

          <div className="rounded-xl border border-border p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              2 · Discharge summary
            </p>
            {summary ? (
              <>
                <pre className="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap rounded-lg bg-mint p-3 text-[11px] leading-relaxed text-ink">
                  {summary}
                </pre>
                <p className="mt-2 text-[11px] text-marigold-deep">
                  Drafted by AI from the ward record. A doctor must review every
                  line — especially the medicines — and sign it before it is given
                  to the patient.
                </p>
              </>
            ) : (
              <Button className="mt-2 w-full" size="sm" variant="outline"
                      onClick={draftSummary} disabled={busy}>
                {busy ? <Loader2 className="animate-spin" /> : <FileText />}
                Draft summary
              </Button>
            )}
          </div>

          <div className="rounded-xl border border-border p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-faint">
              3 · Release the bed
            </p>
            <Input className="mt-2" value={finalDiagnosis}
                   placeholder="Final diagnosis"
                   onChange={(e) => setFinalDiagnosis(e.target.value)} />
            <Button className="mt-2 w-full" size="sm" onClick={completeDischarge}
                    disabled={busy || !invoice}>
              {busy ? <Loader2 className="animate-spin" /> : <LogOut />}
              Complete discharge
            </Button>
            {!invoice && (
              <p className="mt-1.5 text-[11px] text-ink-muted">
                Raise the final bill first — charges cannot be added once the
                admission is closed.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------- panel
export function WardPanel() {
  const [wards, setWards] = useState<WardBoard[] | null>(null);
  const [alerts, setAlerts] = useState<DeterioratingPatient[]>([]);
  const [sheet, setSheet] = useState<Sheet>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [board, deteriorating] = await Promise.all([
        staffApi.wardBoard(),
        staffApi.deterioratingPatients(),
      ]);
      setWards(board.wards);
      setAlerts(deteriorating.patients);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the ward board.");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const scores = useMemo(
    () => new Map(alerts.map((a) => [a.admission_id, a])),
    [alerts]
  );

  return (
    <div className="space-y-5">
      {error && (
        <Card className="border-clay/30 bg-clay/5 p-4 text-sm text-clay">{error}</Card>
      )}

      {alerts.length > 0 && (
        <Card className={cn(
          "border-2",
          alerts.some((a) => a.risk === "critical")
            ? "border-clay bg-clay/5" : "border-marigold bg-marigold/5"
        )}>
          <CardContent className="p-4">
            <p className="flex items-center gap-2 font-display text-sm font-semibold text-ink">
              <AlertTriangle className="h-4 w-4 text-clay" />
              {alerts.length} patient{alerts.length === 1 ? "" : "s"} needing review
            </p>
            <ul className="mt-2 space-y-1.5">
              {alerts.map((a) => (
                <li key={a.admission_id} className="flex flex-wrap items-center gap-2 text-sm">
                  <span className={cn("rounded px-2 py-0.5 text-xs font-bold",
                                      NEWS_BANDS[a.risk].className)}>
                    NEWS2 {a.news2_score}
                  </span>
                  <span className="font-medium text-ink">{a.patient_name}</span>
                  <span className="text-xs text-ink-muted">{a.ward} · {a.bed}</span>
                  <span className="w-full text-xs text-ink-muted sm:w-auto">
                    {a.response}
                  </span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {wards === null ? (
        <div className="space-y-4">
          {[0, 1].map((i) => <Skeleton key={i} className="h-44 rounded-xl" />)}
        </div>
      ) : (
        wards.map((ward) => (
          <Card key={ward.id}>
            <CardContent className="p-4">
              <div className="mb-3 flex flex-wrap items-baseline gap-2">
                <h3 className="font-display text-sm font-semibold text-pine">
                  {ward.name}
                </h3>
                <span className="rounded bg-mint px-1.5 py-0.5 text-[10px] font-medium text-pine">
                  {WARD_TYPE_LABEL[ward.ward_type]}
                </span>
                <span className="text-xs text-ink-muted">
                  {ward.occupied}/{ward.total_beds} occupied
                </span>
                <span className="ml-auto text-xs text-ink-faint">
                  {formatINR(ward.daily_rate_paise)}/day
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
                {ward.beds.map((bed) => {
                  const alert = bed.occupant ? scores.get(bed.occupant.admission_id) : undefined;
                  return (
                    <button
                      key={bed.id}
                      onClick={() =>
                        setSheet(
                          bed.occupant
                            ? { kind: "bed", bed, ward }
                            : bed.status === "vacant"
                              ? { kind: "admit", bed, ward }
                              : null
                        )
                      }
                      disabled={!bed.occupant && bed.status !== "vacant"}
                      className={cn(
                        "flex h-[104px] w-full flex-col rounded-xl border p-2.5 text-left transition",
                        BED_STATUS_STYLE[bed.status],
                        alert?.risk === "critical" && "ring-2 ring-clay"
                      )}
                    >
                      <div className="flex items-center gap-1">
                        <span className="font-display text-xs font-semibold text-pine">
                          {bed.label}
                        </span>
                        {bed.oxygen && <Droplet className="h-3 w-3 text-pine/40" />}
                        {alert && (
                          <span className={cn(
                            "ml-auto rounded px-1.5 py-0.5 text-[10px] font-bold leading-none",
                            NEWS_BANDS[alert.risk].className
                          )}>
                            {alert.news2_score}
                          </span>
                        )}
                      </div>
                      {bed.occupant ? (
                        <div className="mt-1 min-w-0 flex-1">
                          <p className="truncate text-[13px] font-medium leading-tight text-ink">
                            {bed.occupant.patient_name}
                          </p>
                          <p className="truncate text-[11px] text-ink-muted">
                            {bed.occupant.age}
                            {bed.occupant.gender.charAt(0).toUpperCase()} · Day{" "}
                            {dayOfStay(bed.occupant.admitted_at)}
                          </p>
                          <p className="mt-0.5 truncate text-[10px] text-ink-faint">
                            {bed.occupant.diagnosis || bed.occupant.ip_number}
                          </p>
                          {bed.occupant.on_leave && (
                            <p className="mt-0.5 text-[10px] font-semibold text-marigold-deep">On leave</p>
                          )}
                        </div>
                      ) : (
                        <div className="mt-1 flex flex-1 flex-col items-center justify-center">
                          <span className="text-[11px] capitalize text-ink-faint">
                            {bed.status === "vacant" ? "Free" : bed.status}
                          </span>
                          {bed.status === "vacant" && (
                            <span className="mt-0.5 flex items-center gap-0.5 text-[10px] font-medium text-pine">
                              Admit <ArrowRight className="h-2.5 w-2.5" />
                            </span>
                          )}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        ))
      )}

      <AnimatePresence>
        {sheet && (
          <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-4 sm:items-center"
               onClick={() => setSheet(null)}>
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="max-h-[88vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"
            >
              {sheet.kind === "admit" ? (
                <AdmitSheet bed={sheet.bed} ward={sheet.ward}
                            onClose={() => setSheet(null)}
                            onDone={() => { setSheet(null); void load(); }} />
              ) : (
                <BedSheet bed={sheet.bed} ward={sheet.ward}
                          onClose={() => setSheet(null)}
                          onChanged={() => { setSheet(null); void load(); }} />
              )}
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
}
