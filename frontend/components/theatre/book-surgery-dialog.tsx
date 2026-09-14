"use client";

/**
 * Booking a case for theatre.
 *
 * The side is its own choice with nothing selected. A form that opens on
 * "Left" books left knees, and the slip, the checklist and the operation
 * note all copy whatever was chosen here.
 *
 * A room that is already taken is refused by the server; the message says
 * which case holds it, and the doctor can book anyway when two lists sharing
 * a theatre is deliberate.
 */
import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { ApiError, staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { Consultant } from "@/lib/appointmentTypes";
import type { BedOccupant } from "@/lib/ipdTypes";
import type { Operation, Surgery, TheatreOptions, TheatreRoom } from "@/lib/theatreTypes";
import { fromHospitalInput } from "@/lib/theatreTypes";
import { hospitalToday } from "@/lib/format";
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

export interface BookingPatient {
  admission_id: string;
  patient_name: string;
  ip_number: string;
  diagnosis?: string | null;
}

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

export function BookSurgeryDialog({
  open,
  onClose,
  onBooked,
  patient: preset,
}: {
  open: boolean;
  onClose: () => void;
  onBooked: (surgery: Surgery) => void;
  /** Book for this admission. Without it, the dialog asks which inpatient. */
  patient?: BookingPatient;
}) {
  const { user } = useAuth();
  const [options, setOptions] = useState<TheatreOptions | null>(null);
  const [rooms, setRooms] = useState<TheatreRoom[]>([]);
  const [consultants, setConsultants] = useState<Consultant[]>([]);
  const [inpatients, setInpatients] = useState<BedOccupant[]>([]);

  const [patient, setPatient] = useState<BookingPatient | null>(preset ?? null);
  const [operationQuery, setOperationQuery] = useState("");
  const [operation, setOperation] = useState<Operation | null>(null);
  const [suggestions, setSuggestions] = useState<Operation[]>([]);
  const [side, setSide] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [surgeon, setSurgeon] = useState("");
  const [assistants, setAssistants] = useState("");
  const [anaesthetist, setAnaesthetist] = useState("");
  const [anaesthesia, setAnaesthesia] = useState("");
  const [roomId, setRoomId] = useState("");
  const [when, setWhen] = useState(`${hospitalToday(1)}T09:00`);
  const [minutes, setMinutes] = useState("");
  const [priority, setPriority] = useState("elective");
  const [notes, setNotes] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [overlap, setOverlap] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setPatient(preset ?? null);
    setOperationQuery("");
    setOperation(null);
    setSide("");
    setDiagnosis(preset?.diagnosis ?? "");
    setSurgeon(user?.role === "doctor" ? user.full_name : "");
    setAssistants("");
    setAnaesthetist("");
    setAnaesthesia("");
    setRoomId("");
    setWhen(`${hospitalToday(1)}T09:00`);
    setMinutes("");
    setPriority("elective");
    setNotes("");
    setError(null);
    setOverlap(null);

    void staffApi.theatreOptions().then(setOptions).catch(() => undefined);
    void staffApi.theatreRooms().then(setRooms).catch(() => undefined);
    void staffApi.consultants({ active_only: true }).then(setConsultants).catch(() => undefined);
    if (!preset) {
      void staffApi
        .wardBoard()
        .then(({ wards }) =>
          setInpatients(
            wards.flatMap((ward) => ward.beds.map((bed) => bed.occupant)).filter(
              (item): item is BedOccupant => item !== null
            )
          )
        )
        .catch(() => undefined);
    }
  }, [open, preset, user]);

  useEffect(() => {
    const term = operationQuery.trim();
    if (!open || term.length < 2 || operation?.name === term) {
      setSuggestions([]);
      return;
    }
    const timer = setTimeout(() => {
      void staffApi
        .theatreOperations({ q: term, limit: 8 })
        .then(setSuggestions)
        .catch(() => setSuggestions([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [open, operation, operationQuery]);

  const surgeonId = useMemo(
    () => consultants.find((item) => item.full_name === surgeon.trim())?.id ?? null,
    [consultants, surgeon]
  );

  async function submit(allowOverlap: boolean) {
    setError(null);
    if (!patient) return setError("Choose the patient.");
    if (!operation && !operationQuery.trim()) {
      return setError("Choose an operation from the list, or type what is being done.");
    }
    if (!side) return setError("Choose the side.");
    if (!surgeon.trim()) return setError("Name the operating surgeon.");
    if (!when) return setError("Choose the date and time.");

    setBusy(true);
    try {
      const surgery = await staffApi.bookSurgery({
        admission_id: patient.admission_id,
        operation_id: operation?.id ?? null,
        operation_name: operation ? null : operationQuery.trim(),
        laterality: side,
        diagnosis: diagnosis.trim() || null,
        surgeon_consultant_id: surgeonId,
        surgeon_name: surgeon.trim(),
        assistants: assistants.split(",").map((item) => item.trim()).filter(Boolean),
        anaesthetist_name: anaesthetist.trim() || null,
        anaesthesia_type: anaesthesia || null,
        room_id: roomId || null,
        scheduled_at: fromHospitalInput(when),
        expected_minutes: minutes ? Number(minutes) : null,
        priority,
        notes: notes.trim() || null,
        allow_overlap: allowOverlap,
      });
      onBooked(surgery);
    } catch (err) {
      const message = err instanceof Error ? err.message : "The case could not be booked.";
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
      <DialogContent className="max-h-[92dvh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Book for theatre</DialogTitle>
          <DialogDescription>
            {patient
              ? `${patient.patient_name} · ${patient.ip_number}`
              : "Choose the inpatient, the operation and the side."}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-2">
          {!preset && (
            <div className="sm:col-span-2">
              <Field label="Patient">
                <select
                  className={SELECT}
                  value={patient?.admission_id ?? ""}
                  onChange={(event) => {
                    const found = inpatients.find((item) => item.admission_id === event.target.value);
                    setPatient(
                      found
                        ? { admission_id: found.admission_id, patient_name: found.patient_name,
                            ip_number: found.ip_number, diagnosis: found.diagnosis }
                        : null
                    );
                    if (found?.diagnosis && !diagnosis) setDiagnosis(found.diagnosis);
                  }}
                >
                  <option value="">Choose an admitted patient…</option>
                  {inpatients.map((item) => (
                    <option key={item.admission_id} value={item.admission_id}>
                      {item.patient_name} · {item.ip_number} · {item.doctor}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
          )}

          <div className="relative sm:col-span-2">
            <Field label="Operation" hint={operation ? `${operation.code} · about ${operation.default_minutes} min` : "Search the operation list, or type a procedure not on it"}>
              <Input
                value={operationQuery}
                placeholder="Total knee replacement…"
                onChange={(event) => {
                  setOperationQuery(event.target.value);
                  setOperation(null);
                }}
              />
            </Field>
            {suggestions.length > 0 && (
              <ul className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border border-border bg-white shadow-lg">
                {suggestions.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className="flex w-full justify-between px-3 py-2 text-left text-sm hover:bg-mint"
                      onClick={() => {
                        setOperation(item);
                        setOperationQuery(item.name);
                        setMinutes(String(item.default_minutes));
                        setSuggestions([]);
                      }}
                    >
                      <span>{item.name}</span>
                      <span className="text-xs text-ink-faint">{item.default_minutes} min</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="sm:col-span-2">
            <span className="text-xs font-medium text-ink-muted">Side</span>
            <div className="mt-1 flex flex-wrap gap-2">
              {(options?.laterality ?? []).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setSide(item)}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-sm font-medium transition",
                    side === item
                      ? "border-pine bg-pine text-mint"
                      : "border-border bg-white text-ink hover:border-pine/40"
                  )}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div className="sm:col-span-2">
            <Field label="Diagnosis">
              <Input value={diagnosis} onChange={(event) => setDiagnosis(event.target.value)} />
            </Field>
          </div>

          <Field label="Surgeon">
            <Input list="theatre-surgeons" value={surgeon} onChange={(event) => setSurgeon(event.target.value)} />
            <datalist id="theatre-surgeons">
              {consultants.map((item) => (
                <option key={item.id} value={item.full_name} />
              ))}
            </datalist>
          </Field>
          <Field label="Assistants" hint="Separate names with commas">
            <Input value={assistants} onChange={(event) => setAssistants(event.target.value)} />
          </Field>
          <Field label="Anaesthetist">
            <Input value={anaesthetist} onChange={(event) => setAnaesthetist(event.target.value)} />
          </Field>
          <Field label="Anaesthesia">
            <select className={SELECT} value={anaesthesia} onChange={(event) => setAnaesthesia(event.target.value)}>
              <option value="">Not decided yet</option>
              {(options?.anaesthesia_types ?? []).map((item) => (
                <option key={item} value={item}>{item}</option>
              ))}
            </select>
          </Field>

          <Field label="Date and time (hospital time)">
            <Input type="datetime-local" value={when} onChange={(event) => setWhen(event.target.value)} />
          </Field>
          <Field label="Expected duration (minutes)">
            <Input type="number" min={5} max={1440} value={minutes} placeholder="From the operation list"
                   onChange={(event) => setMinutes(event.target.value)} />
          </Field>
          <Field label="Theatre">
            <select className={SELECT} value={roomId} onChange={(event) => setRoomId(event.target.value)}>
              <option value="">Not assigned yet</option>
              {rooms.map((item) => (
                <option key={item.id} value={item.id}>{item.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Priority" hint={priority === "emergency" ? "An emergency may go in before the pre-op checklist is signed." : undefined}>
            <select className={SELECT} value={priority} onChange={(event) => setPriority(event.target.value)}>
              <option value="elective">Elective</option>
              <option value="emergency">Emergency</option>
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="Notes for theatre">
              <Input value={notes} onChange={(event) => setNotes(event.target.value)} />
            </Field>
          </div>
        </div>

        {overlap && (
          <div className="rounded-md border border-marigold/40 bg-marigold/10 p-3 text-sm text-marigold-deep">
            <p className="flex items-start gap-2"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />{overlap}</p>
            <Button size="sm" variant="outline" className="mt-2" disabled={busy} onClick={() => void submit(true)}>
              Book anyway
            </Button>
          </div>
        )}
        {error && <p className="text-sm text-clay">{error}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={busy}>Cancel</Button>
          <Button onClick={() => void submit(false)} disabled={busy}>
            {busy && <Loader2 className="h-4 w-4 animate-spin" />} Book case
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
