"use client";

/**
 * Registering tests for a patient.
 *
 * Billing is chosen here rather than afterwards, because a sample sent with
 * no bill is a test nobody charges for. A patient with an open admission
 * defaults to the admission; the counter bills everyone else. Staff without
 * counter rights — the ward and the bench — bill to the admission or leave
 * the tests for the counter, and the option they cannot use is shown
 * disabled with the reason, not hidden.
 */
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, Search, X } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { Consultant } from "@/lib/appointmentTypes";
import type { PatientCard } from "@/lib/emrTypes";
import type { LabBilling, LabPriority, LabRequest, LabTest } from "@/lib/labTypes";
import { canBillAtCounter } from "@/lib/labTypes";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export interface RegisterPrefill {
  patient: { id: string; name: string; uhid: string | null; age: number; gender: string };
  admission?: { id: string; ip_number: string } | null;
  tests?: { test_id: string; order_item_id?: string | null }[];
  order_id?: string | null;
  consultation_id?: string | null;
  referred_by?: string | null;
  priority?: LabPriority;
  clinical_notes?: string | null;
}

type Picked = RegisterPrefill["patient"];
type Line = { test_id: string; order_item_id?: string | null };

const SELECT =
  "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-pine/30";

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-ink-muted">{label}</span>
      {children}
      {hint && <span className="block text-[11px] text-ink-faint">{hint}</span>}
    </label>
  );
}

export function RegisterLabDialog({
  open,
  onClose,
  onRegistered,
  prefill,
}: {
  open: boolean;
  onClose: () => void;
  onRegistered: (request: LabRequest) => void;
  /** Keep this object stable while the dialog is open: a new one resets the form. */
  prefill?: RegisterPrefill | null;
}) {
  const { user } = useAuth();
  const counter = canBillAtCounter(user?.role);
  const [tests, setTests] = useState<LabTest[]>([]);
  const [consultants, setConsultants] = useState<Consultant[]>([]);
  const [patientQuery, setPatientQuery] = useState("");
  const [matches, setMatches] = useState<PatientCard[]>([]);
  const [patient, setPatient] = useState<Picked | null>(null);
  const [admission, setAdmission] = useState<{ id: string; ip_number: string; billable?: boolean } | null>(null);
  const [testQuery, setTestQuery] = useState("");
  const [chosen, setChosen] = useState<Line[]>([]);
  const [billing, setBilling] = useState<LabBilling>("invoice");
  const [referredBy, setReferredBy] = useState("");
  const [consultantId, setConsultantId] = useState("");
  const [priority, setPriority] = useState<LabPriority>("routine");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setBusy(false);
    setPatient(prefill?.patient ?? null);
    setAdmission(prefill?.admission ?? null);
    setChosen(prefill?.tests ?? []);
    setReferredBy(prefill?.referred_by ?? "");
    setConsultantId("");
    setPriority(prefill?.priority ?? "routine");
    setNotes(prefill?.clinical_notes ?? "");
    setPatientQuery("");
    setMatches([]);
    setTestQuery("");
    setBilling(prefill?.admission ? "ipd" : counter ? "invoice" : "unbilled");
    void staffApi.labTests().then(setTests).catch(() => setTests([]));
    void staffApi.consultants({ active_only: true }).then(setConsultants).catch(() => setConsultants([]));
  }, [open, prefill, counter]);

  // Looked up rather than trusted from an order, which may be days old.
  useEffect(() => {
    if (!open || !patient) return;
    let live = true;
    staffApi
      .labPatientContext(patient.id)
      .then((context) => {
        if (!live) return;
        setAdmission(context.admission);
        if (context.admission && context.admission.billable) setBilling("ipd");
        else setBilling((current) => (current === "ipd" ? (counter ? "invoice" : "unbilled") : current));
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [open, patient, counter]);

  useEffect(() => {
    if (patient || patientQuery.trim().length < 2) {
      setMatches([]);
      return;
    }
    const timer = setTimeout(() => {
      void staffApi.searchCounterPatients(patientQuery.trim()).then(setMatches).catch(() => setMatches([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [patientQuery, patient]);

  const byId = useMemo(() => new Map(tests.map((test) => [test.id, test])), [tests]);
  const available = useMemo(() => {
    const needle = testQuery.trim().toLowerCase();
    return tests
      .filter((test) => !chosen.some((line) => line.test_id === test.id))
      .filter((test) => !needle || test.name.toLowerCase().includes(needle) || test.code.toLowerCase().includes(needle))
      .slice(0, needle ? 12 : 8);
  }, [tests, chosen, testQuery]);
  const unpriced =
    billing === "unbilled"
      ? []
      : chosen
          .map((line) => byId.get(line.test_id))
          .filter((test): test is LabTest => Boolean(test) && !test?.service_code);

  async function submit() {
    if (!patient || chosen.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const created = await staffApi.registerLab({
        patient_id: patient.id,
        tests: chosen,
        billing,
        admission_id: admission?.id ?? null,
        consultation_id: prefill?.consultation_id ?? null,
        order_id: prefill?.order_id ?? null,
        referred_by: referredBy.trim() || null,
        consultant_id: consultantId || null,
        priority,
        clinical_notes: notes.trim() || null,
      });
      onRegistered(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The tests could not be registered.");
    } finally {
      setBusy(false);
    }
  }

  const billingChoices: { value: LabBilling; label: string; disabled: boolean; why?: string }[] = [
    { value: "invoice", label: "Counter bill", disabled: !counter, why: "needs counter rights" },
    {
      value: "ipd",
      label: admission ? `Admission ${admission.ip_number}` : "Admission",
      disabled: !admission || admission.billable === false,
      why: !admission ? "not admitted" : "final bill already raised",
    },
    { value: "unbilled", label: "Leave for the counter", disabled: false },
  ];

  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="max-h-[92dvh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Register tests</DialogTitle>
          <DialogDescription>Choose the patient and tests. A lab number is issued and the tests are billed now.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <Field label="Patient">
            {patient ? (
              <div className="flex items-center justify-between rounded-lg border border-border bg-mint/40 px-3 py-2">
                <div>
                  <p className="text-sm font-medium text-ink">{patient.name}</p>
                  <p className="text-xs text-ink-muted">
                    {patient.uhid ?? "No UHID"} · {patient.age} y · {patient.gender}
                    {admission ? ` · admitted ${admission.ip_number}` : ""}
                  </p>
                </div>
                {!prefill?.patient && (
                  <button
                    type="button"
                    className="rounded p-1 text-ink-faint hover:bg-white hover:text-clay"
                    onClick={() => {
                      setPatient(null);
                      setAdmission(null);
                    }}
                    aria-label="Choose a different patient"
                  >
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
            ) : (
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-faint" />
                <Input
                  autoFocus
                  className="pl-8"
                  placeholder="UHID, phone number or name"
                  value={patientQuery}
                  onChange={(event) => setPatientQuery(event.target.value)}
                />
                {matches.length > 0 && (
                  <div className="absolute z-20 mt-1 max-h-60 w-full overflow-y-auto rounded-lg border border-border bg-white shadow-lg">
                    {matches.map((match) => (
                      <button
                        key={match.id}
                        type="button"
                        className="block w-full px-3 py-2 text-left text-sm hover:bg-mint"
                        onClick={() =>
                          setPatient({ id: match.id, name: match.name, uhid: match.uhid ?? null, age: match.age, gender: match.gender })
                        }
                      >
                        <span className="font-medium text-ink">{match.name}</span>{" "}
                        <span className="text-xs text-ink-muted">
                          {match.uhid ?? ""} · {match.age} y · {match.phone_number}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Field>

          <Field label="Tests">
            <div className="space-y-2">
              {chosen.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {chosen.map((line) => {
                    const test = byId.get(line.test_id);
                    return (
                      <span
                        key={line.test_id}
                        className={cn(
                          "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs",
                          billing !== "unbilled" && test && !test.service_code
                            ? "border-clay/40 bg-clay/5 text-clay"
                            : "border-pine/20 bg-mint text-pine"
                        )}
                      >
                        {test?.name ?? "Test"}
                        {line.order_item_id && <span className="text-[10px] text-ink-faint">(ordered)</span>}
                        <button
                          type="button"
                          onClick={() => setChosen((current) => current.filter((entry) => entry.test_id !== line.test_id))}
                          aria-label={`Remove ${test?.name ?? "test"}`}
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}
              <Input placeholder="Search tests by name or code" value={testQuery} onChange={(event) => setTestQuery(event.target.value)} />
              <div className="flex flex-wrap gap-1.5">
                {available.map((test) => (
                  <button
                    key={test.id}
                    type="button"
                    onClick={() => {
                      setChosen((current) => [...current, { test_id: test.id }]);
                      setTestQuery("");
                    }}
                    className="rounded-full border border-border bg-white px-2.5 py-1 text-xs text-ink-muted transition hover:border-pine/40 hover:text-pine"
                  >
                    + {test.name}
                  </button>
                ))}
              </div>
            </div>
          </Field>

          <Field label="Billing">
            <div className="flex flex-wrap gap-2">
              {billingChoices.map((choice) => (
                <button
                  key={choice.value}
                  type="button"
                  disabled={choice.disabled}
                  onClick={() => setBilling(choice.value)}
                  title={choice.disabled ? choice.why : undefined}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-sm transition disabled:cursor-not-allowed disabled:opacity-40",
                    billing === choice.value ? "border-pine bg-pine text-mint" : "border-border bg-white text-ink-muted hover:border-pine/40"
                  )}
                >
                  {choice.label}
                  {choice.disabled && choice.why ? <span className="ml-1 text-[10px]">({choice.why})</span> : null}
                </button>
              ))}
            </div>
          </Field>
          {unpriced.length > 0 && (
            <p className="flex items-start gap-1.5 rounded-md bg-clay/10 px-3 py-2 text-xs text-clay">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              No price code is set for {unpriced.map((test) => test.name).join(", ")}. Leave these for the counter, or ask for a
              price code to be set in the test list.
            </p>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Referring doctor">
              <select
                className={SELECT}
                value={consultantId}
                onChange={(event) => {
                  setConsultantId(event.target.value);
                  const found = consultants.find((entry) => entry.id === event.target.value);
                  if (found) setReferredBy(found.full_name);
                }}
              >
                <option value="">From the consultant register…</option>
                {consultants.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {entry.full_name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Or type the name">
              <Input value={referredBy} onChange={(event) => setReferredBy(event.target.value)} placeholder="Outside doctor" />
            </Field>
            <Field label="Priority">
              <select className={SELECT} value={priority} onChange={(event) => setPriority(event.target.value as LabPriority)}>
                <option value="routine">Routine</option>
                <option value="urgent">Urgent</option>
                <option value="stat">STAT</option>
              </select>
            </Field>
            <Field label="Clinical notes">
              <Input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Optional" />
            </Field>
          </div>

          {error && <p className="rounded-md bg-clay/10 px-3 py-2 text-sm text-clay">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button disabled={busy || !patient || chosen.length === 0 || unpriced.length > 0} onClick={() => void submit()}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Register {chosen.length || ""} test{chosen.length === 1 ? "" : "s"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
