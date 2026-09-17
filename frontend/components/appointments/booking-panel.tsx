"use client";

/**
 * Booking an appointment.
 *
 * The order of the form is the order of the conversation at the counter:
 * who is it for, which doctor, when. Patient first, because the answer to
 * "when can they come" depends on nothing else and the clerk already has the
 * patient on the phone.
 *
 * A caller need not be a patient. Somebody rings for Tuesday morning; the
 * clerk should not have to register a stranger to write that down, because
 * that fills the register with no-shows and makes a second record the next
 * time they ring. Searching first is still the default, so a returning
 * patient is linked rather than duplicated — but "not on the list" is a
 * normal answer here, not a dead end.
 *
 * Slots are shown as a grid of times rather than a time picker. A picker
 * accepts 09:07 on a Sunday and then fails validation; a grid of the times
 * that actually exist cannot express an impossible booking in the first
 * place, and it answers "how full is Tuesday" at a glance.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { CalendarPlus, Loader2, PhoneCall, Search, Sparkles } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type { Consultant, Slot } from "@/lib/types/appointments";
import type { PatientCard, VisitType } from "@/lib/types/emr";
import { formatHospitalDate, formatHospitalTime, hospitalToday } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const VISIT_TYPES: { value: VisitType; label: string }[] = [
  { value: "new", label: "New" },
  { value: "follow_up", label: "Follow-up" },
  { value: "review", label: "Review" },
  { value: "procedure", label: "Procedure" },
];

export interface Caller {
  name: string;
  phone_number: string;
}

function PatientPicker({
  chosen,
  caller,
  onChoose,
  onCaller,
}: {
  chosen: PatientCard | null;
  caller: Caller | null;
  onChoose: (patient: PatientCard | null) => void;
  onCaller: (caller: Caller | null) => void;
}) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<PatientCard[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const query = term.trim();
    if (query.length < 2 || chosen || caller) {
      setResults([]);
      return;
    }
    // Debounced: a clerk types a UHID faster than a round trip, and firing
    // per keystroke means the answer to an earlier prefix can land last.
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        setResults(await staffApi.searchCounterPatients(query));
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [term, chosen, caller]);

  if (caller) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-marigold-deep/25 bg-marigold/10 px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{caller.name}</p>
          <p className="text-[11px] text-marigold-deep">
            {caller.phone_number} · not registered — UHID issued when they arrive
          </p>
        </div>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-xs"
          onClick={() => {
            onCaller(null);
            setTerm("");
          }}
        >
          Change
        </Button>
      </div>
    );
  }

  if (chosen) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-pine/20 bg-mint px-3 py-2">
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-ink">{chosen.name}</p>
          <p className="text-[11px] text-ink-faint">
            {chosen.uhid} · {chosen.age} · {chosen.phone_number}
          </p>
        </div>
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-xs"
          onClick={() => {
            onChoose(null);
            setTerm("");
          }}
        >
          Change
        </Button>
      </div>
    );
  }

  return (
    <div>
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
        <Input
          value={term}
          onChange={(event) => setTerm(event.target.value)}
          placeholder="UHID, phone or name"
          className="h-9 pl-8 text-sm"
          autoFocus
        />
        {searching && (
          <Loader2 className="absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-ink-faint" />
        )}
      </div>
      {results.length > 0 && (
        <ul className="mt-1 max-h-44 overflow-y-auto rounded-lg border border-border">
          {results.map((patient) => (
            <li key={patient.id}>
              <button
                type="button"
                onClick={() => onChoose(patient)}
                className="flex w-full items-baseline gap-2 border-b border-border px-3 py-1.5 text-left last:border-b-0 hover:bg-mint"
              >
                <span className="text-sm text-ink">{patient.name}</span>
                <span className="text-[11px] text-ink-faint">
                  {patient.uhid} · {patient.phone_number}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {term.trim().length >= 2 && !searching && (
        <CallerFallback term={term} matched={results.length > 0} onCaller={onCaller} />
      )}
    </div>
  );
}

/**
 * "They are not on the list" — the normal case for a phone booking.
 *
 * Shown alongside any search results rather than only when there are none,
 * because a caller sharing a household phone with an existing patient is
 * common and the clerk, not the search, decides whether this is the same
 * person.
 */
function CallerFallback({
  term,
  matched,
  onCaller,
}: {
  term: string;
  matched: boolean;
  onCaller: (caller: Caller) => void;
}) {
  const looksLikePhone = /^\d{10,}$/.test(term.trim());
  const [name, setName] = useState(looksLikePhone ? "" : term.trim());
  const [phone, setPhone] = useState(looksLikePhone ? term.trim() : "");
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-1.5 flex w-full items-center gap-1.5 rounded-lg border border-dashed
                   border-border px-3 py-2 text-left text-[11px] text-ink-muted
                   transition hover:border-pine/40 hover:text-pine"
      >
        <PhoneCall className="h-3.5 w-3.5 shrink-0" />
        {matched
          ? "Not one of these — book a new caller"
          : "Nobody on the register. Book them anyway from a name and number."}
      </button>
    );
  }

  const ready = name.trim().length >= 2 && phone.trim().length >= 10;

  return (
    <div className="mt-1.5 space-y-2 rounded-lg border border-pine/15 bg-mint/50 p-2.5">
      <p className="text-[11px] text-ink-muted">
        No UHID yet — it is issued when they arrive and are registered.
      </p>
      <div className="grid grid-cols-2 gap-2">
        <Input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Caller's name"
          className="h-8 text-sm"
        />
        <Input
          value={phone}
          inputMode="numeric"
          onChange={(event) => setPhone(event.target.value)}
          placeholder="Mobile number"
          className="h-8 text-sm"
        />
      </div>
      <Button
        size="sm"
        variant="outline"
        disabled={!ready}
        className="h-7 w-full text-xs"
        onClick={() => onCaller({ name: name.trim(), phone_number: phone.trim() })}
      >
        Use these details
      </Button>
    </div>
  );
}


export function BookingPanel({ onBooked }: { onBooked?: () => void }) {
  const [consultants, setConsultants] = useState<Consultant[]>([]);
  const [consultantId, setConsultantId] = useState("");
  const [day, setDay] = useState(() => hospitalToday(1));
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [chosenSlot, setChosenSlot] = useState<string | null>(null);
  const [patient, setPatient] = useState<PatientCard | null>(null);
  const [caller, setCaller] = useState<Caller | null>(null);
  const [visitType, setVisitType] = useState<VisitType>("new");
  const [reason, setReason] = useState("");
  const [nextFree, setNextFree] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  // Remounts the patient search after a booking. Clearing the chosen patient
  // is not enough: the search term lives inside the picker, so the box would
  // still hold the last patient's name and re-run the search behind the
  // confirmation the clerk is reading.
  const [pickerKey, setPickerKey] = useState(0);

  useEffect(() => {
    void (async () => {
      try {
        const list = await staffApi.consultants();
        const active = list.filter((item) => item.is_active);
        setConsultants(active);
        setConsultantId((current) => current || active[0]?.id || "");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load the consultant list.");
      }
    })();
  }, []);

  const loadSlots = useCallback(async () => {
    if (!consultantId) return;
    setSlots(null);
    try {
      const found = await staffApi.appointmentSlots(consultantId, day);
      setSlots(found);
      setError(null);
      // Keep a selection only if it still exists and is still free. This is
      // what lets "next free" jump to another day with its slot already
      // picked, while a slot someone else took in the meantime is dropped
      // rather than booked blind.
      setChosenSlot((current) =>
        current && found.some((slot) => slot.start === current && slot.available)
          ? current
          : null
      );
    } catch (err) {
      setSlots([]);
      setChosenSlot(null);
      setError(err instanceof Error ? err.message : "Could not read that day.");
    }
  }, [consultantId, day]);

  useEffect(() => {
    void loadSlots();
  }, [loadSlots]);

  // Answers "when can they come in" without the clerk clicking through days.
  useEffect(() => {
    if (!consultantId) return;
    void (async () => {
      try {
        const found = await staffApi.nextAppointmentSlot(consultantId);
        setNextFree(found.next_available);
      } catch {
        setNextFree(null);
      }
    })();
  }, [consultantId, done]);

  const consultant = useMemo(
    () => consultants.find((item) => item.id === consultantId),
    [consultants, consultantId]
  );

  const who = patient?.name ?? caller?.name ?? "";

  const book = useCallback(async () => {
    if ((!patient && !caller) || !chosenSlot) return;
    setSaving(true);
    setError(null);
    try {
      const appointment = await staffApi.bookAppointment({
        // One or the other, never both — the API refuses the ambiguity.
        ...(patient ? { patient_id: patient.id } : { caller }),
        consultant_id: consultantId,
        scheduled_start: chosenSlot,
        visit_type: visitType,
        reason: reason.trim() || null,
      });
      setDone(
        `${who} booked with ${appointment.consultant_name}, ` +
          `${formatHospitalDate(appointment.scheduled_start)} at ` +
          `${formatHospitalTime(appointment.scheduled_start)}.`
      );
      setPatient(null);
      setCaller(null);
      setPickerKey((value) => value + 1);
      setReason("");
      setChosenSlot(null);
      await loadSlots();
      onBooked?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The booking did not go through.");
    } finally {
      setSaving(false);
    }
  }, [patient, caller, who, chosenSlot, consultantId, visitType, reason, loadSlots, onBooked]);

  const free = (slots ?? []).filter((slot) => slot.available).length;

  return (
    <section className="rounded-2xl border border-pine/10 bg-white">
      <header className="flex items-center gap-2 border-b border-pine/10 px-4 py-3">
        <CalendarPlus className="h-4 w-4 text-pine" />
        <h2 className="font-display text-sm font-semibold text-pine">Book an appointment</h2>
        {slots && (
          <span className="ml-auto text-[11px] text-ink-faint">
            {free} free of {slots.length}
          </span>
        )}
      </header>

      <div className="space-y-3 p-4">
        <div>
          <Label className="text-[11px] uppercase tracking-wide text-ink-faint">Patient</Label>
          <div className="mt-1">
            <PatientPicker
              key={pickerKey}
              chosen={patient}
              caller={caller}
              onChoose={setPatient}
              onCaller={setCaller}
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-ink-faint">
              Consultant
            </Label>
            <select
              value={consultantId}
              onChange={(event) => setConsultantId(event.target.value)}
              className="mt-1 h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink"
            >
              {consultants.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.full_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-ink-faint">Day</Label>
            <Input
              type="date"
              value={day}
              min={hospitalToday()}
              onChange={(event) => setDay(event.target.value || hospitalToday(1))}
              className="mt-1 h-9 text-sm"
            />
          </div>
        </div>

        {consultant && (
          <p className="text-[11px] text-ink-faint">
            Sits {consultant.opd_start_time.slice(0, 5)}–{consultant.opd_end_time.slice(0, 5)},{" "}
            {consultant.appointment_minutes} min per patient.
            {nextFree && (
              <button
                type="button"
                onClick={() => {
                  setDay(nextFree.slice(0, 10));
                  setChosenSlot(nextFree);
                }}
                className="ml-1 inline-flex items-center gap-1 font-medium text-pine hover:underline"
              >
                <Sparkles className="h-3 w-3" />
                Next free: {formatHospitalDate(nextFree)} {formatHospitalTime(nextFree)}
              </button>
            )}
          </p>
        )}

        <div>
          <Label className="text-[11px] uppercase tracking-wide text-ink-faint">Slot</Label>
          {slots === null && (
            <p className="mt-1 text-xs text-ink-faint">Reading the day…</p>
          )}
          {slots?.length === 0 && (
            <p className="mt-1 text-xs text-ink-muted">
              {consultant?.full_name ?? "This consultant"} does not sit on this day.
            </p>
          )}
          {slots && slots.length > 0 && (
            <div className="mt-1 grid grid-cols-4 gap-1.5 sm:grid-cols-6">
              {slots.map((slot) => (
                <button
                  key={slot.start}
                  type="button"
                  disabled={!slot.available}
                  onClick={() => setChosenSlot(slot.start)}
                  className={cn(
                    "tabular rounded border px-1 py-1.5 text-[11px] font-medium transition",
                    slot.available
                      ? "border-border bg-white text-ink hover:border-pine hover:text-pine"
                      : "cursor-not-allowed border-transparent bg-mint-card text-ink-faint line-through",
                    chosenSlot === slot.start && "border-pine bg-pine text-white hover:text-white"
                  )}
                  title={
                    slot.available
                      ? undefined
                      : slot.past
                        ? "Already gone"
                        : "Booked"
                  }
                >
                  {formatHospitalTime(slot.start)}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-ink-faint">Type</Label>
            <select
              value={visitType}
              onChange={(event) => setVisitType(event.target.value as VisitType)}
              className="mt-1 h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink"
            >
              {VISIT_TYPES.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-ink-faint">
              Reason (optional)
            </Label>
            <Input
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Knee pain review"
              className="mt-1 h-9 text-sm"
            />
          </div>
        </div>

        {error && <p className="text-xs text-clay">{error}</p>}
        {done && <p className="text-xs text-marigold-deep">{done}</p>}

        <Button
          onClick={() => void book()}
          disabled={(!patient && !caller) || !chosenSlot || saving}
          className="w-full"
        >
          {saving ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
          {chosenSlot
            ? `Book ${formatHospitalTime(chosenSlot)} on ${formatHospitalDate(chosenSlot)}`
            : "Pick a slot"}
        </Button>
      </div>
    </section>
  );
}
