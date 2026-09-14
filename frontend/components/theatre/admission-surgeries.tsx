"use client";

/** The case sheet's theatre tab: every case booked on this admission. */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Plus } from "lucide-react";
import { staffApi } from "@/lib/staffApi";
import { useAuth } from "@/components/dashboard/auth-provider";
import type { Surgery } from "@/lib/theatreTypes";
import {
  SURGERY_STATUS_LABEL,
  SURGERY_STATUS_VARIANT,
  canSchedule,
  checklistSigned,
} from "@/lib/theatreTypes";
import { formatHospitalDate, formatHospitalTime } from "@/lib/format";
import { BookSurgeryDialog, type BookingPatient } from "@/components/theatre/book-surgery-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export function AdmissionSurgeries({
  patient,
  active,
  theatrePath,
}: {
  patient: BookingPatient;
  active: boolean;
  theatrePath: string;
}) {
  const { user } = useAuth();
  const router = useRouter();
  const [cases, setCases] = useState<Surgery[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [booking, setBooking] = useState(false);

  const load = useCallback(async () => {
    try {
      setCases(await staffApi.surgeries({ admission_id: patient.admission_id }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Theatre cases could not be loaded.");
    }
  }, [patient.admission_id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="space-y-3">
      {canSchedule(user?.role) && active && (
        <Button size="sm" onClick={() => setBooking(true)}>
          <Plus className="h-4 w-4" /> Book for theatre
        </Button>
      )}
      {error && <p className="text-sm text-clay">{error}</p>}
      {!cases ? (
        <Skeleton className="h-20 w-full rounded-xl" />
      ) : cases.length === 0 ? (
        <Card><CardContent className="p-4 text-sm text-ink-muted">No theatre cases on this admission.</CardContent></Card>
      ) : (
        cases.map((item) => (
          <Link key={item.id} href={`${theatrePath}/${item.id}`} className="block">
            <Card className="transition hover:border-pine/40">
              <CardContent className="flex flex-wrap items-center gap-3 p-4">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-ink">
                    {item.operation_name} <span className="font-semibold uppercase text-clay">· {item.laterality}</span>
                  </p>
                  <p className="text-xs text-ink-muted">
                    {formatHospitalDate(item.scheduled_at)}, {formatHospitalTime(item.scheduled_at)} ·{" "}
                    {item.room_name ?? "No theatre assigned"} · {item.surgeon_name} · {item.ot_number}
                  </p>
                </div>
                {item.status === "scheduled" && (
                  <span className={checklistSigned(item) ? "text-xs text-pine" : "text-xs text-marigold-deep"}>
                    {checklistSigned(item) ? "Checklist signed" : "Checklist not signed"}
                  </span>
                )}
                {item.priority === "emergency" && <Badge variant="danger" size="sm">Emergency</Badge>}
                <Badge variant={SURGERY_STATUS_VARIANT[item.status]} size="sm">
                  {SURGERY_STATUS_LABEL[item.status]}
                </Badge>
              </CardContent>
            </Card>
          </Link>
        ))
      )}
      <BookSurgeryDialog
        open={booking}
        patient={patient}
        onClose={() => setBooking(false)}
        onBooked={(surgery) => {
          setBooking(false);
          router.push(`${theatrePath}/${surgery.id}`);
        }}
      />
    </div>
  );
}
