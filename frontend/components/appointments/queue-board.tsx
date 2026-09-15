"use client";

/**
 * The day's queue board.
 *
 * This is the screen that answers "who is here and who is next", which at a
 * counter is asked more often than anything else. Three decisions follow
 * from that:
 *
 * **Bookings and walk-ins share one list.** Most of the morning walks in.
 * A board showing only booked patients would show a waiting room that does
 * not exist, so a walk-in appears as a row with a token instead of a time.
 *
 * **The action is a single button, not a menu.** Each row shows the one
 * thing that happens next — check in, call in, finish — because the person
 * using this has a patient standing in front of them.
 *
 * **It refreshes itself.** The doctor's screen and the counter's screen are
 * looking at the same queue from two rooms, and a stale board sends the
 * wrong patient in.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarPlus,
  CheckCircle2,
  ChevronRight,
  Clock,
  RefreshCw,
  UserCheck,
  Users,
  X,
} from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import type {
  AppointmentStatus,
  Board,
  BoardRow,
} from "@/lib/types/appointments";
import { STATUS_LABEL } from "@/lib/types/appointments";
import { DEPARTMENT_LABEL, formatHospitalTime, hospitalToday } from "@/lib/format";
import type { PatientCard } from "@/lib/types/emr";
import { Button } from "@/components/ui/button";
import { ReasonDialog } from "@/components/ui/reason-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const REFRESH_MS = 20000;

/** Colour carries the state, so the board can be read without reading it. */
const STATUS_STYLE: Record<AppointmentStatus, string> = {
  pending: "border-border bg-white text-ink-muted",
  waiting: "border-marigold-deep/30 bg-marigold/10 text-marigold-deep",
  engaged: "border-pine/30 bg-mint text-pine",
  done: "border-border bg-mint-card text-ink-faint",
  cancelled: "border-clay/25 bg-clay/5 text-clay",
};

/** The one thing that happens to this patient next. */
function nextStep(row: BoardRow): { label: string; to: AppointmentStatus } | null {
  if (row.kind === "walk_in") return null; // driven by the consultation itself
  switch (row.status) {
    case "pending":
      // A phone booking has no patient record yet, so arriving means being
      // registered. Saying so on the button matters: the clerk needs to know
      // they are about to be asked for age and gender, not just click once.
      return { label: row.registered ? "Check in" : "Register & check in", to: "waiting" };
    case "waiting":
      return { label: "Call in", to: "engaged" };
    case "engaged":
      return { label: "Finish", to: "done" };
    default:
      return null;
  }
}

function StatusPill({ status }: { status: AppointmentStatus }) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        STATUS_STYLE[status]
      )}
    >
      {STATUS_LABEL[status]}
    </span>
  );
}

function Row({
  row,
  busy,
  onAdvance,
  onCancel,
}: {
  row: BoardRow;
  busy: boolean;
  onAdvance: (row: BoardRow) => void;
  onCancel: (row: BoardRow) => void;
}) {
  const step = nextStep(row);
  const cancellable =
    row.kind === "appointment" && (row.status === "pending" || row.status === "waiting");

  return (
    <li
      className={cn(
        "flex items-center gap-3 border-b border-border px-4 py-2.5 last:border-b-0",
        row.status === "cancelled" && "opacity-60"
      )}
    >
      {/* Time for a booking, token for a walk-in. One column, two meanings —
          which is honest: both answer "when is this patient's turn". */}
      <span className="tabular w-[70px] shrink-0 text-sm font-medium text-pine">
        {row.scheduled_start ? (
          <>
            {formatHospitalTime(row.scheduled_start)}
            {/* Once checked in, a booking is called by token like anyone
                else, so both are shown rather than making the clerk work
                out which queue position "10:20 am" corresponds to. */}
            {row.token_number != null && (
              <span className="block text-[10px] font-normal text-ink-faint">
                token {row.token_number}
              </span>
            )}
          </>
        ) : (
          <span className="text-ink-faint">#{row.token_number ?? "—"}</span>
        )}
      </span>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-ink">
          {row.patient_name}
          {row.kind === "walk_in" && (
            <span className="ml-1.5 text-[11px] font-normal text-ink-faint">walk-in</span>
          )}
        </p>
        <p className="truncate text-[11px] text-ink-faint">
          {row.registered ? (
            row.uhid
          ) : (
            <span className="text-marigold-deep">
              {row.phone_number ?? "phone booking"} · no UHID yet
            </span>
          )}{" "}
          · {row.consultant_name || DEPARTMENT_LABEL[row.department]}
          {row.reason ? ` · ${row.reason}` : ""}
        </p>
      </div>

      <StatusPill status={row.status} />

      {step && (
        <Button
          size="sm"
          variant="outline"
          disabled={busy}
          onClick={() => onAdvance(row)}
          className="h-7 shrink-0 px-2 text-xs"
        >
          {step.label}
          <ChevronRight className="ml-0.5 h-3 w-3" />
        </Button>
      )}
      {cancellable && (
        <button
          type="button"
          disabled={busy}
          onClick={() => onCancel(row)}
          className="shrink-0 rounded p-1 text-ink-faint transition hover:text-clay disabled:opacity-40"
          aria-label={`Cancel ${row.patient_name}'s appointment`}
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </li>
  );
}

/**
 * Registering the caller who has just walked in.
 *
 * Prefilled with what they said on the telephone, because retyping a name
 * the clerk already wrote down is how it gets spelled two different ways.
 * Age and gender are asked here and not at booking: over a phone they are
 * guessed, at the desk they are known.
 */
function RegisterCallerDialog({
  row,
  onCancel,
  onDone,
}: {
  row: BoardRow;
  onCancel: () => void;
  onDone: () => void;
}) {
  const [name, setName] = useState(row.patient_name);
  const [phone, setPhone] = useState(row.phone_number ?? "");
  const [age, setAge] = useState("");
  const [gender, setGender] = useState("female");
  const [city, setCity] = useState("");
  const [matches, setMatches] = useState<PatientCard[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Look the number up once. If this caller turns out to be on the register
  // already, linking that record is far better than issuing them a second
  // UHID — which is the duplicate the old system accumulated for years.
  useEffect(() => {
    if (!row.phone_number) return;
    void (async () => {
      try {
        setMatches(await staffApi.searchCounterPatients(row.phone_number as string));
      } catch {
        setMatches([]);
      }
    })();
  }, [row.phone_number]);

  const submit = useCallback(
    async (payload: Record<string, unknown>) => {
      if (!row.id) return;
      setSaving(true);
      setError(null);
      try {
        await staffApi.checkInAppointment(row.id, payload);
        onDone();
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not check them in.");
      } finally {
        setSaving(false);
      }
    },
    [row.id, onDone]
  );

  const ready = name.trim().length >= 2 && phone.trim().length >= 10 && age !== "";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/20 p-3"
      role="dialog"
      aria-modal="true"
      aria-label="Register this caller"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md space-y-3 rounded-2xl border border-pine/10 bg-white p-4 shadow-lift"
        onClick={(event) => event.stopPropagation()}
      >
        <div>
          <h3 className="font-display text-sm font-semibold text-pine">
            Register {row.patient_name}
          </h3>
          <p className="text-[11px] text-ink-muted">
            Booked by phone with no UHID. Registering issues one and puts them in the queue.
          </p>
        </div>

        {matches.length > 0 && (
          <div className="rounded-lg border border-marigold-deep/25 bg-marigold/10 p-2.5">
            <p className="text-[11px] font-medium text-marigold-deep">
              This number is already on the register. Link instead of creating a second record?
            </p>
            <ul className="mt-1.5 space-y-1">
              {matches.map((match) => (
                <li key={match.id}>
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => void submit({ patient_id: match.id })}
                    className="w-full rounded border border-border bg-white px-2 py-1.5 text-left text-xs hover:border-pine"
                  >
                    <span className="font-medium text-ink">{match.name}</span>{" "}
                    <span className="text-ink-faint">
                      {match.uhid} · {match.age} yrs
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-ink-faint">Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 h-9 text-sm" />
          </div>
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-ink-faint">Mobile</Label>
            <Input
              value={phone}
              inputMode="numeric"
              onChange={(e) => setPhone(e.target.value)}
              className="mt-1 h-9 text-sm"
            />
          </div>
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-ink-faint">Age</Label>
            <Input
              value={age}
              inputMode="numeric"
              onChange={(e) => setAge(e.target.value)}
              className="mt-1 h-9 text-sm"
              autoFocus
            />
          </div>
          <div>
            <Label className="text-[11px] uppercase tracking-wide text-ink-faint">Gender</Label>
            <select
              value={gender}
              onChange={(e) => setGender(e.target.value)}
              className="mt-1 h-9 w-full rounded-md border border-border bg-white px-2 text-sm text-ink"
            >
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="other">Other</option>
            </select>
          </div>
        </div>
        <div>
          <Label className="text-[11px] uppercase tracking-wide text-ink-faint">
            City (optional)
          </Label>
          <Input value={city} onChange={(e) => setCity(e.target.value)} className="mt-1 h-9 text-sm" />
        </div>

        {error && <p className="text-xs text-clay">{error}</p>}

        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
            Cancel
          </Button>
          <Button
            size="sm"
            className="flex-1"
            disabled={!ready || saving}
            onClick={() =>
              void submit({
                new_patient: {
                  name: name.trim(),
                  age: Number(age),
                  gender,
                  phone_number: phone.trim(),
                  city: city.trim() || null,
                },
              })
            }
          >
            {saving ? "Registering…" : "Register & check in"}
          </Button>
        </div>
      </div>
    </div>
  );
}


export function QueueBoard({
  onBook,
  className,
}: {
  onBook?: () => void;
  className?: string;
}) {
  const [day, setDay] = useState(() => hospitalToday());
  const [board, setBoard] = useState<Board | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  // The caller standing at the desk who has to be registered before they can
  // be checked in.
  const [registerFor, setRegisterFor] = useState<BoardRow | null>(null);
  // The booking being cancelled, which needs a written reason like any other
  // undoing of counter work.
  const [cancelling, setCancelling] = useState<BoardRow | null>(null);

  const load = useCallback(async () => {
    try {
      setBoard(await staffApi.queueBoard({ on: day }));
      setError(null);
    } catch (err) {
      // A failed fetch and an empty morning look identical unless one of
      // them says so.
      setError(err instanceof Error ? err.message : "Could not load the board.");
    }
  }, [day]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const advance = useCallback(
    async (row: BoardRow) => {
      const step = nextStep(row);
      if (!row.id || !step) return;
      setBusyId(row.id);
      try {
        if (step.to === "waiting") {
          // Checking in is not a status change: it registers an attendance
          // and allots a token, which the API does in one step. For a phone
          // booking it also creates the patient record.
          if (!row.registered) {
            setRegisterFor(row);
            setBusyId(null);
            return;
          }
          await staffApi.checkInAppointment(row.id);
        } else {
          await staffApi.setAppointmentStatus(row.id, step.to);
        }
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : "That did not go through.");
      } finally {
        setBusyId(null);
      }
    },
    [load]
  );

  const cancel = useCallback((row: BoardRow) => {
    if (!row.id) return;
    setCancelling(row);
  }, []);

  const counts = board?.counts;
  const rows = useMemo(
    () =>
      // Cancelled bookings sink to the bottom: they are kept visible so a
      // patient who turns up anyway can be found, but they are not the queue.
      [...(board?.rows ?? [])].sort(
        (a, b) => Number(a.status === "cancelled") - Number(b.status === "cancelled")
      ),
    [board]
  );

  return (
    <section className={cn("rounded-2xl border border-pine/10 bg-white", className)}>
      <header className="flex flex-wrap items-center gap-2 border-b border-pine/10 px-4 py-3">
        <Users className="h-4 w-4 text-pine" />
        <h2 className="font-display text-sm font-semibold text-pine">Queue board</h2>

        {counts && (
          <span className="flex items-center gap-1.5 text-[11px] text-ink-muted">
            <span className="rounded bg-marigold/15 px-1.5 py-0.5 font-medium text-marigold-deep">
              {counts.waiting} waiting
            </span>
            <span className="rounded bg-mint px-1.5 py-0.5 font-medium text-pine">
              {counts.engaged} in
            </span>
            <span className="rounded bg-mint-card px-1.5 py-0.5 text-ink-faint">
              {counts.done} done
            </span>
          </span>
        )}

        <div className="ml-auto flex items-center gap-1.5">
          <input
            type="date"
            value={day}
            onChange={(event) => setDay(event.target.value || hospitalToday())}
            className="h-7 rounded border border-border bg-white px-2 text-xs text-ink"
            aria-label="Show another day"
          />
          <button
            type="button"
            onClick={() => void load()}
            className="rounded p-1 text-ink-faint transition hover:text-pine"
            aria-label="Refresh the board"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
          {onBook && (
            <Button size="sm" onClick={onBook} className="h-7 px-2 text-xs">
              <CalendarPlus className="mr-1 h-3.5 w-3.5" />
              Book
            </Button>
          )}
        </div>
      </header>

      {error && (
        <p className="border-b border-clay/20 bg-clay/5 px-4 py-2 text-xs text-clay">{error}</p>
      )}

      {!board && !error && (
        <p className="px-4 py-8 text-center text-xs text-ink-faint">Loading the day…</p>
      )}

      {board && rows.length === 0 && (
        <div className="flex flex-col items-center gap-1 px-4 py-10 text-center">
          <Clock className="h-5 w-5 text-ink-faint" />
          <p className="text-sm text-ink-muted">Nobody booked or registered yet.</p>
          <p className="text-[11px] text-ink-faint">
            Walk-ins appear here the moment they are registered at the counter.
          </p>
        </div>
      )}

      {rows.length > 0 && (
        <ul className="max-h-[calc(100vh-320px)] overflow-y-auto">
          {rows.map((row) => (
            <Row
              key={row.id ?? row.visit_id ?? row.patient_id}
              row={row}
              busy={busyId === row.id}
              onAdvance={advance}
              onCancel={cancel}
            />
          ))}
        </ul>
      )}

      <ReasonDialog
        request={
          cancelling
            ? {
                title: `Cancel ${cancelling.patient_name}'s appointment?`,
                detail: "The slot is freed immediately and can be given to someone else.",
                confirmLabel: "Cancel appointment",
                destructive: true,
                run: (reason) =>
                  staffApi.cancelAppointment(cancelling.id as string, reason),
              }
            : null
        }
        onClose={() => setCancelling(null)}
        onDone={() => void load()}
      />

      {registerFor && (
        <RegisterCallerDialog
          row={registerFor}
          onCancel={() => setRegisterFor(null)}
          onDone={() => {
            setRegisterFor(null);
            void load();
          }}
        />
      )}

      <footer className="flex items-center gap-3 border-t border-pine/10 px-4 py-2 text-[11px] text-ink-faint">
        <span className="flex items-center gap-1">
          <UserCheck className="h-3 w-3" /> Check in registers the visit
        </span>
        <span className="flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3" /> Refreshes every 20s
        </span>
      </footer>
    </section>
  );
}
