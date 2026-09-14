"use client";

/**
 * The day's theatre list.
 *
 * Grouped by theatre and in time order, because that is how the OT in-charge
 * reads it: what is in each room, what is next, and whether the patient is
 * ready to be sent for. A case still in theatre from last night stays on the
 * board until it is wheeled out.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { Surgery } from "@/lib/theatreTypes";
import {
  SURGERY_STATUS_LABEL,
  SURGERY_STATUS_VARIANT,
  canSchedule,
  checklistSigned,
  minutesLabel,
} from "@/lib/theatreTypes";
import { formatHospitalDate, formatHospitalTime, hospitalToday } from "@/lib/format";
import { BookSurgeryDialog } from "@/components/theatre/book-surgery-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

const REFRESH_MS = 30000;
const UNASSIGNED = "No theatre assigned";

function shiftDay(day: string, by: number): string {
  const moment = new Date(`${day}T12:00:00Z`);
  moment.setUTCDate(moment.getUTCDate() + by);
  return moment.toISOString().slice(0, 10);
}

function Readiness({ surgery }: { surgery: Surgery }) {
  if (surgery.status !== "scheduled") return null;
  if (checklistSigned(surgery)) {
    return (
      <span className="flex items-center gap-1 text-xs text-pine">
        <CheckCircle2 className="h-3.5 w-3.5" /> Checklist signed
      </span>
    );
  }
  return (
    <span className={cn("flex items-center gap-1 text-xs", surgery.priority === "emergency" ? "text-ink-faint" : "text-marigold-deep")}>
      <AlertTriangle className="h-3.5 w-3.5" /> Checklist not signed
    </span>
  );
}

export function TheatreBoard({ basePath }: { basePath: string }) {
  const { user } = useAuth();
  const router = useRouter();
  const [day, setDay] = useState(hospitalToday());
  const [cases, setCases] = useState<Surgery[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [booking, setBooking] = useState(false);

  const load = useCallback(async () => {
    try {
      setCases(await staffApi.surgeries({ on: day }));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The theatre list could not be loaded.");
    }
  }, [day]);

  useEffect(() => {
    setCases(null);
    void load();
    const timer = setInterval(() => void load(), REFRESH_MS);
    return () => clearInterval(timer);
  }, [load]);

  const groups = useMemo(() => {
    const byRoom = new Map<string, Surgery[]>();
    for (const item of cases ?? []) {
      const key = item.room_name ?? UNASSIGNED;
      byRoom.set(key, [...(byRoom.get(key) ?? []), item]);
    }
    return [...byRoom.entries()].sort(([a], [b]) =>
      a === UNASSIGNED ? 1 : b === UNASSIGNED ? -1 : a.localeCompare(b)
    );
  }, [cases]);

  const count = (status: Surgery["status"]) => (cases ?? []).filter((item) => item.status === status).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 rounded-lg border border-border bg-white p-1">
          <button className="rounded p-1.5 text-ink-muted hover:bg-mint" aria-label="Previous day"
                  onClick={() => setDay((value) => shiftDay(value, -1))}>
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="min-w-[8.5rem] text-center text-sm font-medium text-ink">
            {day === hospitalToday() ? "Today · " : ""}{formatHospitalDate(`${day}T12:00:00+05:30`)}
          </span>
          <button className="rounded p-1.5 text-ink-muted hover:bg-mint" aria-label="Next day"
                  onClick={() => setDay((value) => shiftDay(value, 1))}>
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        {day !== hospitalToday() && (
          <Button size="sm" variant="ghost" onClick={() => setDay(hospitalToday())}>Today</Button>
        )}
        {cases && (
          <p className="text-sm text-ink-muted">
            {cases.length} case{cases.length === 1 ? "" : "s"} · {count("in_theatre")} in theatre ·{" "}
            {count("completed")} done{count("cancelled") ? ` · ${count("cancelled")} cancelled` : ""}
          </p>
        )}
        {canSchedule(user?.role) && (
          <Button size="sm" className="ml-auto" onClick={() => setBooking(true)}>
            <Plus className="h-4 w-4" /> Book a case
          </Button>
        )}
      </div>

      {error && <p className="text-sm text-clay">{error}</p>}

      {!cases ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
      ) : cases.length === 0 ? (
        <Card>
          <CardContent className="p-6 text-center text-sm text-ink-muted">
            No cases booked for this day.
          </CardContent>
        </Card>
      ) : (
        groups.map(([room, items]) => (
          <Card key={room}>
            <CardHeader className="pb-2">
              <CardTitle>{room}</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border p-0">
              {items.map((item) => (
                <Link
                  key={item.id}
                  href={`${basePath}/${item.id}`}
                  className={cn(
                    "grid gap-x-4 gap-y-1 px-4 py-3 transition hover:bg-mint/60 sm:grid-cols-[5.5rem_1fr_auto]",
                    item.status === "cancelled" && "opacity-60"
                  )}
                >
                  <div>
                    <p className="tabular font-display text-base font-semibold text-pine">
                      {formatHospitalTime(item.scheduled_at)}
                    </p>
                    <p className="text-[11px] text-ink-faint">{minutesLabel(item.expected_minutes)}</p>
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-ink">
                      {item.operation_name}{" "}
                      <span className="font-semibold uppercase text-clay">· {item.laterality}</span>
                    </p>
                    <p className="text-sm text-ink-muted">
                      {item.patient?.name ?? "—"} · {item.ip_number ?? "Day case"} · {item.surgeon_name}
                      {item.anaesthesia_type ? ` · ${item.anaesthesia_type}` : ""}
                    </p>
                    <p className="text-[11px] text-ink-faint">{item.ot_number}</p>
                  </div>
                  <div className="flex flex-col items-start gap-1 sm:items-end">
                    <div className="flex gap-1">
                      {item.priority === "emergency" && <Badge variant="danger" size="sm">Emergency</Badge>}
                      <Badge variant={SURGERY_STATUS_VARIANT[item.status]} size="sm">
                        {SURGERY_STATUS_LABEL[item.status]}
                      </Badge>
                    </div>
                    <Readiness surgery={item} />
                  </div>
                </Link>
              ))}
            </CardContent>
          </Card>
        ))
      )}

      <BookSurgeryDialog
        open={booking}
        onClose={() => setBooking(false)}
        onBooked={(surgery) => {
          setBooking(false);
          router.push(`${basePath}/${surgery.id}`);
        }}
      />
    </div>
  );
}
