"use client";

/**
 * The inpatient case sheet.
 *
 * One admission, everything about it, on one screen: who the patient is and
 * where they are lying, what the doctor and the nurses have written, the
 * observations, the drug chart, and the discharge. The ward board has linked
 * here since it was built; until now the link went nowhere.
 *
 * Two things the old system did that staff rely on:
 *
 * * **Several patients open at once.** A doctor on a round moves bed to bed
 *   and back. The strip across the top keeps every case sheet opened this
 *   session one click away, and switching between them never loses a note:
 *   the pad saves whatever was typed on the way out.
 * * **Every document knows whose it is.** The doctor writes the admission note,
 *   progress notes and discharge summary; the nurse writes the assessment and
 *   shift notes. Opening the other profession's document shows it read-only
 *   with the reason, rather than refusing to show it at all.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  BedDouble,
  CheckCircle2,
  Circle,
  FilePen,
  Loader2,
  Plus,
  X,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { PadDocumentSummary } from "@/lib/padTypes";
import type { AdmissionChart, DischargeType } from "@/lib/ipdTypes";
import { DISCHARGE_TYPE_LABEL, NEWS_BANDS, dayOfStay } from "@/lib/ipdTypes";
import { formatDateTime } from "@/lib/format";
import { VisitPad } from "@/components/pad/visit-pad";
import { DrugChartView } from "@/components/ipd/drug-chart";
import { AdmissionSurgeries } from "@/components/theatre/admission-surgeries";
import { PatientForms } from "@/components/pad/patient-forms";
import { PatientFiles } from "@/components/patient/patient-files";
import { LabResultsPanel } from "@/components/lab/lab-results-panel";
import { RecordsBundle } from "@/components/ipd/records-bundle";
import { LeavePanel } from "@/components/ipd/leave-panel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

/* ------------------------------------------------------- open patients -- */

interface OpenSheet {
  id: string;
  name: string;
  bed: string;
}

const OPEN_KEY = "satya.caseSheets.open";
const MAX_OPEN = 8;

function readOpen(): OpenSheet[] {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(OPEN_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeOpen(list: OpenSheet[]) {
  try {
    sessionStorage.setItem(OPEN_KEY, JSON.stringify(list.slice(-MAX_OPEN)));
  } catch {
    /* private mode or storage blocked: the strip simply does not persist */
  }
}

/* ------------------------------------------------------------ helpers -- */

const money = (paise: number) =>
  `₹${(paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

type DocState = "signed" | "draft" | "missing";

function stateOf(documents: PadDocumentSummary[], type: string): DocState {
  const ofType = documents.filter((item) => item.document_type === type);
  if (ofType.some((item) => item.status === "signed")) return "signed";
  if (ofType.some((item) => item.status === "draft")) return "draft";
  return "missing";
}

function StateMark({ state }: { state: DocState }) {
  if (state === "signed") return <CheckCircle2 className="h-4 w-4 text-pine" />;
  if (state === "draft") return <FilePen className="h-4 w-4 text-marigold-deep" />;
  return <Circle className="h-4 w-4 text-ink-faint" />;
}

const STATE_LABEL: Record<DocState, string> = {
  signed: "Signed",
  draft: "Draft in progress",
  missing: "Not started",
};

/* ------------------------------------------------------- note documents -- */

/**
 * A kind of note there are many of — progress notes, nursing notes. A list of
 * what has been written, newest first, and the pad for the one being read or
 * written beside it.
 */
function NoteStream({
  admissionId,
  documentType,
  label,
  documents,
  active,
  onChanged,
}: {
  admissionId: string;
  documentType: string;
  label: string;
  documents: PadDocumentSummary[];
  active: boolean;
  onChanged: () => void;
}) {
  // null: nothing open. "open": the caller's own unfinished note, or a new one.
  const [selected, setSelected] = useState<string | null>(null);
  const notes = documents
    .filter((item) => item.document_type === documentType)
    .sort((a, b) => (b.signed_at ?? b.created_at).localeCompare(a.signed_at ?? a.created_at));

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
      <div className="space-y-2">
        {active && (
          <Button size="sm" className="w-full" onClick={() => setSelected("open")}>
            <Plus /> Write a {label.toLowerCase()}
          </Button>
        )}
        {notes.length === 0 && (
          <p className="px-1 text-xs text-ink-muted">No {label.toLowerCase()}s yet.</p>
        )}
        <ul className="space-y-1">
          {notes.map((note) => (
            <li key={note.id}>
              <button
                type="button"
                onClick={() => setSelected(note.id)}
                className={cn(
                  "w-full rounded-lg border px-3 py-2 text-left transition",
                  selected === note.id
                    ? "border-pine/40 bg-mint"
                    : "border-border bg-white hover:border-pine/25"
                )}
              >
                <span className="flex items-center gap-1.5 text-xs font-medium text-ink">
                  <StateMark state={note.status === "signed" ? "signed" : "draft"} />
                  {formatDateTime(note.signed_at ?? note.created_at)}
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-ink-faint">
                  {note.signed_by_name ?? note.author_name}
                  {note.version > 1 ? ` · corrected v${note.version}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="min-w-0">
        {selected === null ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-ink-muted">
              Pick a {label.toLowerCase()} to read it
              {active ? `, or write a new one.` : "."}
            </CardContent>
          </Card>
        ) : (
          <VisitPad
            key={`${documentType}:${selected}`}
            admissionId={selected === "open" ? admissionId : undefined}
            documentId={selected === "open" ? undefined : selected}
            documentType={documentType}
            onChanged={onChanged}
          />
        )}
      </div>
    </div>
  );
}

/** Two documents under one tab, switched by pills: one single, one stream. */
function DocumentGroup({
  admissionId,
  single,
  stream,
  documents,
  active,
  onChanged,
}: {
  admissionId: string;
  single: { type: string; label: string };
  stream: { type: string; label: string };
  documents: PadDocumentSummary[];
  active: boolean;
  onChanged: () => void;
}) {
  const [view, setView] = useState<"single" | "stream">("single");
  return (
    <div className="space-y-3">
      <div className="flex w-fit gap-1 rounded-lg bg-mint p-1">
        {([
          ["single", single],
          ["stream", stream],
        ] as const).map(([key, item]) => (
          <button
            key={key}
            type="button"
            onClick={() => setView(key)}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition",
              view === key ? "bg-white text-pine shadow-sm" : "text-ink-muted hover:text-pine"
            )}
          >
            {key === "single" && <StateMark state={stateOf(documents, item.type)} />}
            {key === "single" ? item.label : `${item.label}s`}
            {key === "stream" && (
              <span className="tabular text-[11px] text-ink-faint">
                {documents.filter((doc) => doc.document_type === item.type).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {view === "single" ? (
        <VisitPad
          key={single.type}
          admissionId={admissionId}
          documentType={single.type}
          onChanged={onChanged}
        />
      ) : (
        <NoteStream
          admissionId={admissionId}
          documentType={stream.type}
          label={stream.label}
          documents={documents}
          active={active}
          onChanged={onChanged}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------- vitals -- */

function VitalsTab({
  chart,
  active,
  onRecorded,
}: {
  chart: AdmissionChart;
  active: boolean;
  onRecorded: () => void;
}) {
  const blank = {
    respiratory_rate: "", spo2_percent: "", systolic_bp: "", diastolic_bp: "",
    pulse: "", temperature_c: "", consciousness: "A", on_oxygen: false,
  };
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rows = [...chart.vitals].sort((a, b) => b.recorded_at.localeCompare(a.recorded_at));

  async function record() {
    setBusy(true);
    setError(null);
    const number = (value: string) => (value.trim() === "" ? undefined : Number(value));
    try {
      await staffApi.recordVitals(chart.admission.id, {
        respiratory_rate: number(form.respiratory_rate),
        spo2_percent: number(form.spo2_percent),
        systolic_bp: number(form.systolic_bp),
        diastolic_bp: number(form.diastolic_bp),
        pulse: number(form.pulse),
        temperature_c: number(form.temperature_c),
        consciousness: form.consciousness,
        on_oxygen: form.on_oxygen,
      });
      setForm(blank);
      onRecorded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The observations were not saved.");
    } finally {
      setBusy(false);
    }
  }

  const input =
    "h-8 w-full rounded-md border border-input bg-white px-2 text-sm text-ink focus-visible:border-pine focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pine/20";

  return (
    <div className="space-y-4">
      {active && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>Record observations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
              {([
                ["respiratory_rate", "RR /min"],
                ["spo2_percent", "SpO2 %"],
                ["systolic_bp", "Systolic"],
                ["diastolic_bp", "Diastolic"],
                ["pulse", "Pulse"],
                ["temperature_c", "Temp °C"],
              ] as const).map(([key, label]) => (
                <label key={key} className="block">
                  <span className="mb-0.5 block text-[11px] text-ink-muted">{label}</span>
                  <input
                    inputMode="decimal"
                    value={form[key]}
                    onChange={(event) => setForm({ ...form, [key]: event.target.value })}
                    className={input}
                  />
                </label>
              ))}
              <label className="block">
                <span className="mb-0.5 block text-[11px] text-ink-muted">AVPU</span>
                <select
                  value={form.consciousness}
                  onChange={(event) => setForm({ ...form, consciousness: event.target.value })}
                  className={input}
                >
                  <option value="A">Alert</option>
                  <option value="C">New confusion</option>
                  <option value="V">Voice</option>
                  <option value="P">Pain</option>
                  <option value="U">Unresponsive</option>
                </select>
              </label>
              <label className="flex items-end gap-1.5 pb-1.5 text-xs text-ink">
                <input
                  type="checkbox"
                  checked={form.on_oxygen}
                  onChange={(event) => setForm({ ...form, on_oxygen: event.target.checked })}
                  className="h-4 w-4 accent-pine"
                />
                On oxygen
              </label>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <Button size="sm" disabled={busy} onClick={() => void record()}>
                {busy && <Loader2 className="animate-spin" />} Save observations
              </Button>
              <span className="text-[11px] text-ink-faint">
                The early warning score is calculated when these are saved.
              </span>
            </div>
            {error && <p className="mt-2 text-xs text-clay">{error}</p>}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="overflow-x-auto p-0">
          {rows.length === 0 ? (
            <p className="p-6 text-center text-sm text-ink-muted">No observations recorded yet.</p>
          ) : (
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-ink-faint">
                  <th className="px-3 py-2 font-medium">When</th>
                  <th className="px-2 py-2 font-medium">NEWS2</th>
                  <th className="px-2 py-2 font-medium">RR</th>
                  <th className="px-2 py-2 font-medium">SpO2</th>
                  <th className="px-2 py-2 font-medium">BP</th>
                  <th className="px-2 py-2 font-medium">Pulse</th>
                  <th className="px-2 py-2 font-medium">Temp</th>
                  <th className="px-2 py-2 font-medium">AVPU</th>
                  <th className="px-3 py-2 font-medium">By</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="tabular border-b border-border last:border-0">
                    <td className="whitespace-nowrap px-3 py-2 text-xs text-ink-muted">
                      {formatDateTime(row.recorded_at)}
                    </td>
                    <td className="px-2 py-2">
                      {row.news2_score !== null && row.news2_risk && (
                        <span className={cn("rounded px-1.5 py-0.5 text-xs font-bold", NEWS_BANDS[row.news2_risk].className)}>
                          {row.news2_score}
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2">{row.respiratory_rate ?? "—"}</td>
                    <td className="px-2 py-2">
                      {row.spo2_percent ?? "—"}
                      {row.on_oxygen ? <span className="ml-1 text-[10px] text-ink-faint">O₂</span> : null}
                    </td>
                    <td className="px-2 py-2">
                      {row.systolic_bp ? `${row.systolic_bp}/${row.diastolic_bp ?? "—"}` : "—"}
                    </td>
                    <td className="px-2 py-2">{row.pulse ?? "—"}</td>
                    <td className="px-2 py-2">{row.temperature_c ?? "—"}</td>
                    <td className="px-2 py-2">{row.consciousness ?? "—"}</td>
                    <td className="px-3 py-2 text-xs text-ink-muted">{row.recorded_by_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------- discharge -- */

function DischargePanel({
  chart,
  summarySigned,
  onDischarged,
}: {
  chart: AdmissionChart;
  summarySigned: boolean;
  onDischarged: () => void;
}) {
  const [type, setType] = useState<DischargeType>("routine");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { admission } = chart;

  if (admission.status === "discharged") {
    return (
      <Card>
        <CardContent className="flex items-center gap-2 p-4 text-sm text-ink">
          <CheckCircle2 className="h-4 w-4 text-pine" />
          Discharged {admission.discharged_at ? formatDateTime(admission.discharged_at) : ""}
          {admission.discharge_type ? ` · ${DISCHARGE_TYPE_LABEL[admission.discharge_type]}` : ""}
        </CardContent>
      </Card>
    );
  }

  // Going home or to another hospital needs the signed summary; the server
  // enforces this too. The other three cannot wait for paperwork.
  const needsSummary = type === "routine" || type === "transferred_out";
  const blocked = needsSummary && !summarySigned;

  async function discharge() {
    setBusy(true);
    setError(null);
    try {
      await staffApi.dischargePatient(admission.id, { discharge_type: type });
      setConfirming(false);
      onDischarged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The patient was not discharged.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle>Discharge the patient</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={type}
            onChange={(event) => setType(event.target.value as DischargeType)}
            className="h-9 rounded-md border border-input bg-white px-2 text-sm text-ink"
          >
            {(Object.keys(DISCHARGE_TYPE_LABEL) as DischargeType[]).map((key) => (
              <option key={key} value={key}>{DISCHARGE_TYPE_LABEL[key]}</option>
            ))}
          </select>
          <Button disabled={blocked || busy} onClick={() => setConfirming(true)}>
            Discharge
          </Button>
        </div>
        {blocked && (
          <p className="flex items-center gap-1.5 text-xs text-marigold-deep">
            <AlertTriangle className="h-3.5 w-3.5" />
            Sign the discharge summary above first. A patient going home or to another
            hospital leaves with one.
          </p>
        )}
        {error && <p className="text-xs text-clay">{error}</p>}
      </CardContent>

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Discharge {chart.patient?.name}?</DialogTitle>
            <DialogDescription>
              {DISCHARGE_TYPE_LABEL[type]}. The bed is released for cleaning, active medicines are
              stopped, and the final bed charges are posted. This cannot be undone from here.
            </DialogDescription>
          </DialogHeader>
          {error && <p className="text-xs text-clay">{error}</p>}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirming(false)}>Not yet</Button>
            <Button disabled={busy} onClick={() => void discharge()}>
              {busy && <Loader2 className="animate-spin" />} Discharge
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/* ---------------------------------------------------------- the sheet -- */

export function CaseSheet({
  admissionId,
  basePath,
  homePath,
}: {
  admissionId: string;
  /** Where a case sheet lives, so the open-patient strip can link to others. */
  basePath: string;
  /** Where closing the last open case sheet goes. */
  homePath: string;
}) {
  const router = useRouter();
  const [chart, setChart] = useState<AdmissionChart | null>(null);
  const [documents, setDocuments] = useState<PadDocumentSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<OpenSheet[]>([]);

  const load = useCallback(async () => {
    try {
      const [loaded, docs] = await Promise.all([
        staffApi.admissionChart(admissionId),
        staffApi.padDocuments({ admission_id: admissionId }),
      ]);
      setChart(loaded);
      setDocuments(docs);
      setError(null);

      const entry: OpenSheet = {
        id: admissionId,
        name: loaded.patient?.name ?? loaded.admission.ip_number,
        bed: loaded.current_bed ? `${loaded.current_bed.ward} ${loaded.current_bed.bed}` : loaded.admission.ip_number,
      };
      const list = readOpen().filter((item) => item.id !== admissionId);
      const next = [...list, entry];
      writeOpen(next);
      setOpen(next.slice(-MAX_OPEN));
    } catch (err) {
      setError(err instanceof Error ? err.message : "This case sheet could not be loaded.");
    }
  }, [admissionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const close = (id: string) => {
    const remaining = readOpen().filter((item) => item.id !== id);
    writeOpen(remaining);
    setOpen(remaining);
    if (id === admissionId) {
      const next = remaining[remaining.length - 1];
      router.push(next ? `${basePath}/${next.id}` : homePath);
    }
  };

  const summarySigned = useMemo(
    () => stateOf(documents, "ipd_discharge_summary") === "signed",
    [documents]
  );

  if (error && !chart) {
    return (
      <Card className="border-clay/30 bg-clay/5">
        <CardContent className="flex items-center justify-between gap-3 p-4">
          <p className="text-sm text-clay">{error}</p>
          <Link href={homePath}>
            <Button size="sm" variant="outline">Back to the ward</Button>
          </Link>
        </CardContent>
      </Card>
    );
  }

  if (!chart) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-10 w-full rounded-lg" />
        <Skeleton className="h-28 w-full rounded-xl" />
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }

  const { admission, patient, current_bed: bed } = chart;
  const active = admission.status === "admitted" || admission.status === "discharge_initiated";
  const latest = [...chart.vitals].sort((a, b) => b.recorded_at.localeCompare(a.recorded_at))[0];
  const allergies = (admission.allergies ?? []).filter(Boolean);
  const activeMeds = chart.medications.filter((item) => item.status === "active");

  const checklist: { type: string; label: string; tab: string }[] = [
    { type: "ipd_admission_note", label: "Admission note", tab: "doctor" },
    { type: "ipd_nursing_assessment", label: "Nursing assessment", tab: "nursing" },
    { type: "ipd_discharge_summary", label: "Discharge summary", tab: "discharge" },
  ];

  return (
    <div className="space-y-4">
      {/* ------------------------------------------- open patients strip -- */}
      {open.length > 1 && (
        <nav aria-label="Open case sheets" className="flex gap-1.5 overflow-x-auto pb-1">
          {open.map((item) => (
            <div
              key={item.id}
              className={cn(
                "flex shrink-0 items-center gap-1 rounded-lg border pl-3 pr-1 text-sm",
                item.id === admissionId
                  ? "border-pine bg-white text-pine shadow-sm"
                  : "border-border bg-mint/60 text-ink-muted hover:border-pine/30"
              )}
            >
              <Link href={`${basePath}/${item.id}`} className="py-1.5">
                <span className="font-medium">{item.name}</span>
                <span className="ml-1.5 text-[11px] text-ink-faint">{item.bed}</span>
              </Link>
              <button
                type="button"
                onClick={() => close(item.id)}
                className="rounded p-1 text-ink-faint hover:text-clay"
                aria-label={`Close ${item.name}`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ))}
        </nav>
      )}

      {chart.readmission_of && (
        <p className="flex items-start gap-1.5 rounded-md bg-marigold/15 px-3 py-2 text-sm text-marigold-deep">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          Re-admission: discharged {chart.readmission_of.days_since} day(s) earlier from {chart.readmission_of.ip_number}
          {chart.readmission_of.final_diagnosis ? ` (${chart.readmission_of.final_diagnosis})` : ""}.
        </p>
      )}
      {(chart.leaves ?? []).some((leave) => !leave.returned_at) && (
        <p className="rounded-md bg-marigold/15 px-3 py-2 text-sm font-medium text-marigold-deep">
          The patient is on leave. Doses due while away cannot be signed. Mark the return on the Overview tab.
        </p>
      )}

      {/* ------------------------------------------------------ header -- */}
      <Card>
        <CardContent className="flex flex-wrap items-start gap-x-6 gap-y-3 p-4">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-xl font-semibold text-pine">{patient?.name}</h1>
              <Badge variant={active ? "success" : "outline"} size="sm">
                {admission.status === "discharge_initiated"
                  ? "Discharge initiated"
                  : admission.status === "admitted"
                    ? "Admitted"
                    : "Discharged"}
              </Badge>
            </div>
            <p className="mt-0.5 text-sm text-ink-muted">
              {patient?.age} y · {patient?.gender} · UHID {patient?.uhid ?? "—"} · {admission.ip_number}
            </p>
            <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-faint">
              <BedDouble className="h-3.5 w-3.5" />
              {bed ? `${bed.ward} · bed ${bed.bed}` : "No bed"}
              {" · "}Day {dayOfStay(admission.admitted_at)} · under {admission.admitting_doctor_name}
            </p>
          </div>

          {/* Allergies sit in the header, in red, on every tab. They are the
              one fact nobody should have to go looking for. */}
          <div className="max-w-sm">
            {allergies.length > 0 ? (
              <p className="flex items-start gap-1.5 rounded-md bg-clay/10 px-2.5 py-1.5 text-sm font-medium text-clay">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                Allergic to {allergies.join(", ")}
              </p>
            ) : (
              <p className="text-xs text-ink-faint">No allergies recorded on admission</p>
            )}
          </div>

          {latest?.news2_score !== null && latest?.news2_risk && (
            <div className="text-right">
              <span className={cn("rounded px-2 py-1 text-sm font-bold", NEWS_BANDS[latest.news2_risk].className)}>
                NEWS2 {latest.news2_score}
              </span>
              <p className="mt-1 text-[11px] text-ink-faint">{formatDateTime(latest.recorded_at)}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* -------------------------------------------------------- tabs -- */}
      <Tabs defaultValue="overview">
        <TabsList className="mb-3 w-fit justify-start overflow-x-auto">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="doctor">Doctor&apos;s notes</TabsTrigger>
          <TabsTrigger value="nursing">Nursing</TabsTrigger>
          <TabsTrigger value="vitals">Vitals</TabsTrigger>
          <TabsTrigger value="medicines">Medicines</TabsTrigger>
          <TabsTrigger value="theatre">Theatre</TabsTrigger>
          <TabsTrigger value="forms">Consents &amp; certificates</TabsTrigger>
          <TabsTrigger value="lab">Lab</TabsTrigger>
          <TabsTrigger value="files">Files</TabsTrigger>
          <TabsTrigger value="records">Records file</TabsTrigger>
          <TabsTrigger value="discharge">Discharge</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="grid gap-4 lg:grid-cols-2">
          <div className="lg:col-span-2">
            <LeavePanel chart={chart} onChanged={() => void load()} />
          </div>
          <Card>
            <CardHeader className="pb-2"><CardTitle>Admission</CardTitle></CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p><span className="text-ink-muted">Reason: </span>{admission.reason_for_admission || "—"}</p>
              <p><span className="text-ink-muted">Provisional diagnosis: </span>{admission.provisional_diagnosis || "—"}</p>
              <p><span className="text-ink-muted">Final diagnosis: </span>{admission.final_diagnosis || "Set when the discharge summary is signed"}</p>
              <p className="text-xs text-ink-faint">Admitted {formatDateTime(admission.admitted_at)}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>The record</CardTitle></CardHeader>
            <CardContent className="space-y-2">
              {checklist.map((item) => {
                const state = stateOf(documents, item.type);
                return (
                  <div key={item.type} className="flex items-center gap-2 text-sm">
                    <StateMark state={state} />
                    <span className="flex-1 text-ink">{item.label}</span>
                    <span className="text-xs text-ink-muted">{STATE_LABEL[state]}</span>
                  </div>
                );
              })}
              <div className="flex items-center gap-2 text-sm">
                <Circle className="h-4 w-4 text-transparent" />
                <span className="flex-1 text-ink">Progress notes</span>
                <span className="tabular text-xs text-ink-muted">
                  {documents.filter((d) => d.document_type === "ipd_progress_note" && d.status === "signed").length} signed
                </span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Circle className="h-4 w-4 text-transparent" />
                <span className="flex-1 text-ink">Nursing notes</span>
                <span className="tabular text-xs text-ink-muted">
                  {documents.filter((d) => d.document_type === "ipd_nursing_note" && d.status === "signed").length} signed
                </span>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>Medicines running</CardTitle></CardHeader>
            <CardContent>
              {activeMeds.length === 0 ? (
                <p className="text-sm text-ink-muted">None active.</p>
              ) : (
                <ul className="space-y-1 text-sm">
                  {activeMeds.map((item) => (
                    <li key={item.id} className="text-ink">
                      {item.drug_name} {item.strength ?? ""}{" "}
                      <span className="text-ink-muted">{item.dose} · {item.route} · {item.frequency_code}</span>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2"><CardTitle>Running bill</CardTitle></CardHeader>
            <CardContent className="space-y-1 text-sm">
              <div className="flex justify-between"><span className="text-ink-muted">Charges so far</span><span className="tabular">{money(chart.bill.total_paise)}</span></div>
              <div className="flex justify-between"><span className="text-ink-muted">Advance paid</span><span className="tabular">{money(chart.bill.advance_paid_paise)}</span></div>
              <div className="flex justify-between font-medium"><span>Balance</span><span className="tabular">{money(chart.bill.balance_paise)}</span></div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="doctor">
          <DocumentGroup
            admissionId={admissionId}
            single={{ type: "ipd_admission_note", label: "Admission note" }}
            stream={{ type: "ipd_progress_note", label: "Progress note" }}
            documents={documents}
            active={active}
            onChanged={() => void load()}
          />
        </TabsContent>

        <TabsContent value="nursing">
          <DocumentGroup
            admissionId={admissionId}
            single={{ type: "ipd_nursing_assessment", label: "Initial assessment" }}
            stream={{ type: "ipd_nursing_note", label: "Nursing note" }}
            documents={documents}
            active={active}
            onChanged={() => void load()}
          />
        </TabsContent>

        <TabsContent value="vitals">
          <VitalsTab chart={chart} active={active} onRecorded={() => void load()} />
        </TabsContent>

        <TabsContent value="medicines">
          <DrugChartView admissionId={admissionId} active={active} onChanged={() => void load()} />
        </TabsContent>

        <TabsContent value="theatre">
          <AdmissionSurgeries
            patient={{
              admission_id: admissionId,
              patient_name: patient?.name ?? "",
              ip_number: admission.ip_number,
              diagnosis: admission.provisional_diagnosis,
            }}
            active={active}
            theatrePath={basePath.startsWith("/ward") ? "/ward/theatre" : "/theatre"}
          />
        </TabsContent>

        <TabsContent value="forms">
          {patient && (
            <PatientForms
              patientId={patient.id}
              admissionId={admissionId}
              active={active}
              title="Consents and certificates for this admission"
            />
          )}
        </TabsContent>

        <TabsContent value="discharge" className="space-y-4">
          <VisitPad
            key="ipd_discharge_summary"
            admissionId={admissionId}
            documentType="ipd_discharge_summary"
            onChanged={() => void load()}
          />
          <DischargePanel
            chart={chart}
            summarySigned={summarySigned}
            onDischarged={() => void load()}
          />
        </TabsContent>
        <TabsContent value="lab">
          {patient && (
            <LabResultsPanel patientId={patient.id} admissionId={admissionId} title="Lab results for this admission" />
          )}
        </TabsContent>

        <TabsContent value="files">
          {patient && (
            <PatientFiles patientId={patient.id} admissionId={admissionId} title="Files for this admission" />
          )}
        </TabsContent>

        <TabsContent value="records">
          <RecordsBundle admissionId={admissionId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
