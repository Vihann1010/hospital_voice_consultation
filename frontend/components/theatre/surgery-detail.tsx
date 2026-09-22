"use client";

/**
 * One theatre case: who, what, which side, its theatre times and its notes.
 *
 * The side is printed as large as the patient's name, in red, on every view
 * of the case. The theatre times are one button each, pressed as they happen;
 * a time that was missed can be entered afterwards, and the server refuses a
 * time out of order or in the future.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Circle,
  Clock,
  Loader2,
  Printer,
  XCircle,
} from "lucide-react";
import { ApiError, staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import { useModules } from "@/components/dashboard/modules-provider";
import type { Milestone, Surgery, TheatreDocumentStatus, TheatreRoom } from "@/lib/types/theatre";
import {
  MILESTONES,
  SURGERY_STATUS_LABEL,
  SURGERY_STATUS_VARIANT,
  canRecord,
  canSchedule,
  checklistSigned,
  fromHospitalInput,
  minutesLabel,
  toHospitalInput,
} from "@/lib/types/theatre";
import { formatDateTime, formatHospitalDate, formatHospitalTime } from "@/lib/format";
import { VisitPad } from "@/components/pad/visit-pad";
import { PatientForms } from "@/components/pad/patient-forms";
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
import { Input } from "@/components/ui/input";
import { ReasonDialog, type ReasonRequest } from "@/components/ui/reason-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const SELECT =
  "h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink focus:outline-none focus:ring-2 focus:ring-pine/30";

const THEATRE_CONSENTS = ["consent_surgical", "consent_blood_transfusion", "consent_high_risk"];

function openBlob(blob: Blob) {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

function DocumentMark({ status }: { status: TheatreDocumentStatus }) {
  if (status === "signed") return <CheckCircle2 className="h-3.5 w-3.5 text-pine" />;
  if (status === "draft") return <Circle className="h-3.5 w-3.5 fill-marigold/40 text-marigold-deep" />;
  return <Circle className="h-3.5 w-3.5 text-ink-faint" />;
}

/* ------------------------------------------------------------ reschedule -- */

function RescheduleDialog({
  surgery,
  open,
  onClose,
  onDone,
}: {
  surgery: Surgery;
  open: boolean;
  onClose: () => void;
  onDone: (surgery: Surgery) => void;
}) {
  const { wordsFor } = useModules();
  const words = wordsFor(surgery.department);
  const [rooms, setRooms] = useState<TheatreRoom[]>([]);
  const [when, setWhen] = useState("");
  const [roomId, setRoomId] = useState("");
  const [minutes, setMinutes] = useState("");
  const [priority, setPriority] = useState<string>("elective");
  const [error, setError] = useState<string | null>(null);
  const [overlap, setOverlap] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setWhen(toHospitalInput(surgery.scheduled_at));
    setRoomId(surgery.room_id ?? "");
    setMinutes(String(surgery.expected_minutes));
    setPriority(surgery.priority);
    setError(null);
    setOverlap(null);
    void staffApi.theatreRooms().then(setRooms).catch(() => undefined);
  }, [open, surgery]);

  async function submit(allowOverlap: boolean) {
    setBusy(true);
    setError(null);
    try {
      onDone(
        await staffApi.rescheduleSurgery(surgery.id, {
          scheduled_at: fromHospitalInput(when),
          room_id: roomId || null,
          expected_minutes: Number(minutes) || surgery.expected_minutes,
          priority,
          allow_overlap: allowOverlap,
        })
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "The case could not be changed.";
      if (err instanceof ApiError && err.status === 409 && !allowOverlap && message.includes("already booked")) {
        setOverlap(message);
      } else {
        setError(message);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Change the booking</DialogTitle>
          <DialogDescription>{surgery.ot_number} · {surgery.operation_name}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <label className="block space-y-1">
            <span className="text-xs font-medium text-ink-muted">Date and time (hospital time)</span>
            <Input type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-ink-muted">{words.roomOne}</span>
            <select className={SELECT} value={roomId} onChange={(event) => setRoomId(event.target.value)}>
              <option value="">Not assigned</option>
              {rooms.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-ink-muted">Expected duration (minutes)</span>
            <Input type="number" min={5} max={1440} value={minutes} onChange={(event) => setMinutes(event.target.value)} />
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-ink-muted">Priority</span>
            <select className={SELECT} value={priority} onChange={(event) => setPriority(event.target.value)}>
              <option value="elective">Elective</option>
              <option value="emergency">Emergency — may go in before the checklist is signed</option>
            </select>
          </label>
        </div>
        {overlap && (
          <div className="rounded-md border border-marigold/40 bg-marigold/10 p-3 text-sm text-marigold-deep">
            <p>{overlap}</p>
            <Button size="sm" variant="outline" className="mt-2" disabled={busy} onClick={() => void submit(true)}>
              Keep this time anyway
            </Button>
          </div>
        )}
        {error && <p className="text-sm text-clay">{error}</p>}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Close</Button>
          <Button onClick={() => void submit(false)} disabled={busy || !when}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* --------------------------------------------------------- theatre times -- */

function TheatreTimes({
  surgery,
  mayRecord,
  onRecorded,
}: {
  surgery: Surgery;
  mayRecord: boolean;
  onRecorded: (surgery: Surgery) => void;
}) {
  const { wordsFor } = useModules();
  const words = wordsFor(surgery.department);
  const [busy, setBusy] = useState<Milestone | null>(null);
  const [editing, setEditing] = useState<Milestone | null>(null);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  const gated = surgery.status === "scheduled" && surgery.priority !== "emergency" && !checklistSigned(surgery);

  async function record(key: Milestone, at?: string) {
    setBusy(key);
    setError(null);
    try {
      onRecorded(await staffApi.recordTheatreTime(surgery.id, key, at ? fromHospitalInput(at) : undefined));
      setEditing(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The time could not be recorded.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2"><Clock className="h-4 w-4" /> {words.times}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {gated && mayRecord && (
          <p className="flex items-start gap-1.5 rounded-md bg-marigold/15 px-2.5 py-1.5 text-xs text-marigold-deep">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            The {words.checklist} must be signed before the patient is wheeled in. For an emergency,
            change the booking&apos;s priority first.
          </p>
        )}
        {MILESTONES.filter(({ key }) => !words.skipMilestones.includes(key)).map(({ key, label: base }) => {
          const label = key === "anaesthesia_start_at" ? `${words.anaesthesia} started` : base;
          const at = surgery[key];
          const open =
            !at &&
            (key === "wheel_in_at" ? surgery.status === "scheduled" : surgery.status === "in_theatre");
          return (
            <div key={key} className="flex flex-wrap items-center gap-2 border-b border-border/60 pb-2 last:border-0">
              {at ? (
                <CheckCircle2 className="h-4 w-4 text-pine" />
              ) : (
                <Circle className="h-4 w-4 text-ink-faint" />
              )}
              <span className="flex-1 text-sm text-ink">{label}</span>
              {at ? (
                <span className="tabular text-sm font-medium text-ink">
                  {formatHospitalTime(at)}
                  <span className="ml-1 text-[11px] font-normal text-ink-faint">{formatHospitalDate(at)}</span>
                </span>
              ) : mayRecord && open ? (
                editing === key ? (
                  <span className="flex items-center gap-1">
                    <Input type="datetime-local" className="h-8 w-48" value={value}
                           onChange={(event) => setValue(event.target.value)} />
                    <Button size="sm" disabled={!value || busy !== null} onClick={() => void record(key, value)}>
                      Save
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
                  </span>
                ) : (
                  <span className="flex items-center gap-1">
                    <Button size="sm" disabled={busy !== null || (key === "wheel_in_at" && gated)}
                            onClick={() => void record(key)}>
                      {busy === key && <Loader2 className="h-3.5 w-3.5 animate-spin" />} Now
                    </Button>
                    <Button size="sm" variant="ghost" disabled={busy !== null || (key === "wheel_in_at" && gated)}
                            onClick={() => { setEditing(key); setValue(toHospitalInput(new Date())); }}>
                      Earlier…
                    </Button>
                  </span>
                )
              ) : (
                <span className="text-xs text-ink-faint">—</span>
              )}
            </div>
          );
        })}
        {error && <p className="text-sm text-clay">{error}</p>}
        {surgery.status === "completed" && (
          <div className="grid grid-cols-3 gap-2 pt-1 text-center">
            {([
              [words.durations[0], surgery.durations.theatre_minutes],
              [words.durations[1], surgery.durations.surgery_minutes],
              [words.durations[2], surgery.durations.anaesthesia_minutes],
            ] as const).map(([label, minutes]) => (
              <div key={label} className="rounded-lg bg-mint px-2 py-1.5">
                <p className="tabular text-sm font-semibold text-pine">{minutesLabel(minutes)}</p>
                <p className="text-[10px] uppercase tracking-wide text-ink-faint">{label}</p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ------------------------------------------------------------ the case -- */

export function SurgeryDetail({
  surgeryId,
  caseSheetPath,
  boardPath,
}: {
  surgeryId: string;
  /** Where an admission's case sheet lives in this shell. */
  caseSheetPath: string;
  boardPath: string;
}) {
  const { user } = useAuth();
  const { wordsFor } = useModules();
  const [surgery, setSurgery] = useState<Surgery | null>(null);
  const words = wordsFor(surgery?.department);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [cancelRequest, setCancelRequest] = useState<ReasonRequest | null>(null);
  const [rescheduling, setRescheduling] = useState(false);
  const [printing, setPrinting] = useState(false);

  const load = useCallback(async () => {
    try {
      setSurgery(await staffApi.surgery(surgeryId));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The case could not be loaded.");
    }
  }, [surgeryId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (error && !surgery) {
    return (
      <Card>
        <CardContent className="space-y-2 p-4 text-sm">
          <p className="text-clay">{error}</p>
          <Link href={boardPath} className="text-pine underline">Back to the theatre list</Link>
        </CardContent>
      </Card>
    );
  }
  if (!surgery) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-32 w-full rounded-xl" />
        <Skeleton className="h-72 w-full rounded-xl" />
      </div>
    );
  }

  const mayBook = canSchedule(user?.role);
  const side = surgery.laterality.toUpperCase();
  const sided = ["LEFT", "RIGHT", "BILATERAL"].includes(side);

  return (
    <div className="space-y-4">
      <Link href={boardPath} className="text-sm text-pine hover:underline">← {words.board}</Link>

      <Card>
        <CardContent className="flex flex-wrap items-start gap-x-6 gap-y-3 p-4">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-display text-xl font-semibold text-pine">{surgery.patient?.name}</h1>
              <Badge variant={SURGERY_STATUS_VARIANT[surgery.status]} size="sm">
                {surgery.status === "in_theatre" ? words.inRoom : SURGERY_STATUS_LABEL[surgery.status]}
              </Badge>
              {surgery.priority === "emergency" && <Badge variant="danger" size="sm">Emergency</Badge>}
            </div>
            <p className="text-sm text-ink-muted">
              {surgery.patient?.age} y · {surgery.patient?.gender} · UHID {surgery.patient?.uhid ?? "—"} ·{" "}
              {surgery.admission_id ? (
                <Link href={`${caseSheetPath}/${surgery.admission_id}`} className="text-pine hover:underline">
                  {surgery.ip_number}
                </Link>
              ) : (
                "Day case"
              )}{" "}
              · {surgery.ot_number}
            </p>
            <div className="mt-2 rounded-lg bg-mint px-3 py-2">
              <p className="text-base font-semibold text-ink">{surgery.operation_name}</p>
              {surgery.teeth && (
                <p className="font-display text-lg font-bold tracking-wide text-clay">
                  TEETH: {surgery.teeth}
                </p>
              )}
              {(sided || words.askSide) && (
                <p className={cn("font-display text-lg font-bold tracking-wide", sided ? "text-clay" : "text-ink")}>
                  SIDE: {side}
                </p>
              )}
            </div>
          </div>

          <div className="max-w-sm space-y-2">
            {surgery.allergies.length > 0 ? (
              <p className="flex items-start gap-1.5 rounded-md bg-clay/10 px-2.5 py-1.5 text-sm font-medium text-clay">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                Allergic to {surgery.allergies.join(", ")}
              </p>
            ) : (
              <p className="text-xs text-ink-faint">No allergies recorded on admission</p>
            )}
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={printing}
                      onClick={async () => {
                        setPrinting(true);
                        try { openBlob(await staffApi.surgerySlip(surgery.id)); }
                        catch (err) { setNotice(err instanceof Error ? err.message : "The slip could not be printed."); }
                        finally { setPrinting(false); }
                      }}>
                <Printer className="h-4 w-4" /> {words.slip}
              </Button>
              {mayBook && surgery.status === "scheduled" && (
                <>
                  <Button size="sm" variant="outline" onClick={() => setRescheduling(true)}>
                    <CalendarClock className="h-4 w-4" /> Change booking
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-clay hover:text-clay"
                    onClick={() =>
                      setCancelRequest({
                        title: "Cancel this case",
                        detail: `${surgery.operation_name} (${surgery.laterality}) for ${surgery.patient?.name}. The case stays in the surgical register with the reason.`,
                        confirmLabel: "Cancel case",
                        destructive: true,
                        run: async (reason) => setSurgery(await staffApi.cancelSurgery(surgery.id, reason)),
                      })
                    }
                  >
                    <XCircle className="h-4 w-4" /> Cancel
                  </Button>
                </>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {notice && (
        <p className="flex items-start gap-1.5 rounded-md bg-marigold/15 px-3 py-2 text-sm text-marigold-deep">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {notice}
        </p>
      )}
      {surgery.status === "cancelled" && (
        <p className="rounded-md bg-clay/10 px-3 py-2 text-sm text-clay">
          Cancelled: {surgery.cancel_reason}
        </p>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
        <Card>
          <CardHeader className="pb-2"><CardTitle>Booking</CardTitle></CardHeader>
          <CardContent className="grid gap-x-6 gap-y-1.5 text-sm sm:grid-cols-2">
            {([
              ["Scheduled", `${formatHospitalDate(surgery.scheduled_at)}, ${formatHospitalTime(surgery.scheduled_at)} · ${minutesLabel(surgery.expected_minutes)}`],
              [words.roomOne, surgery.room_name ?? "Not assigned"],
              ["Diagnosis", surgery.diagnosis ?? "—"],
              [words.operator, surgery.surgeon_name],
              ["Assistants", surgery.assistants.join(", ") || "—"],
              [words.anaesthetist, surgery.anaesthetist_name ?? "—"],
              [words.anaesthesia, surgery.anaesthesia_type ?? "Not decided"],
              ["Booked by", `${surgery.booked_by_name ?? "—"} · ${formatDateTime(surgery.created_at)}`],
              ["Billing", surgery.charge_reference ? `Charged to the ${surgery.admission_id ? "admission" : "visit"} (${surgery.charge_reference})` : surgery.status === "completed" ? "Not charged — add to the bill by hand" : "Charged when the patient is wheeled out"],
              ["Notes", surgery.notes ?? "—"],
            ] as const).map(([label, value]) => (
              <p key={label}><span className="text-ink-muted">{label}: </span>{value}</p>
            ))}
          </CardContent>
        </Card>

        <TheatreTimes
          surgery={surgery}
          mayRecord={canRecord(user?.role)}
          onRecorded={(updated) => {
            setSurgery(updated);
            if (updated.charge_note) setNotice(updated.charge_note);
          }}
        />
      </div>

      {surgery.patient && (
        <PatientForms
          patientId={surgery.patient.id}
          surgeryId={surgery.id}
          only={THEATRE_CONSENTS}
          active={surgery.status !== "cancelled"}
          title="Consent for this operation"
        />
      )}

      <Tabs defaultValue={surgery.documents[0]?.document_type}>
        <TabsList className="mb-3 w-fit justify-start overflow-x-auto">
          {surgery.documents.map((item) => (
            <TabsTrigger key={item.document_type} value={item.document_type} className="gap-1.5">
              <DocumentMark status={item.status} /> {item.label}
            </TabsTrigger>
          ))}
        </TabsList>
        {surgery.documents.map((item) => (
          <TabsContent key={item.document_type} value={item.document_type}>
            <VisitPad
              key={item.document_type}
              surgeryId={surgery.id}
              documentType={item.document_type}
              onChanged={() => void load()}
            />
          </TabsContent>
        ))}
      </Tabs>

      <RescheduleDialog
        surgery={surgery}
        open={rescheduling}
        onClose={() => setRescheduling(false)}
        onDone={(updated) => {
          setSurgery(updated);
          setRescheduling(false);
        }}
      />
      <ReasonDialog request={cancelRequest} onClose={() => setCancelRequest(null)} />
    </div>
  );
}
