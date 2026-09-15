/** Appointments, slots and the queue board.
 *
 *  Times cross the wire as ISO strings carrying the hospital's offset
 *  (+05:30), not as bare local times. The browser is not necessarily in
 *  Kanpur — a doctor checking the morning from a phone abroad must see the
 *  hospital's nine o'clock, not their own.
 */
import type { Department } from "@/lib/types/core";
import type { VisitType } from "@/lib/types/emr";

export type AppointmentStatus =
  | "pending"
  | "waiting"
  | "engaged"
  | "done"
  | "cancelled";

/** What the board calls each state. "Engaged" is not a word staff use. */
export const STATUS_LABEL: Record<AppointmentStatus, string> = {
  pending: "Booked",
  waiting: "Waiting",
  engaged: "With the doctor",
  done: "Done",
  cancelled: "Cancelled",
};

export interface Slot {
  start: string;
  end: string;
  available: boolean;
  past: boolean;
  appointment_id?: string | null;
}

export interface Appointment {
  id: string;
  /** Null while the booking is only a phone caller. */
  patient_id?: string | null;
  caller_name?: string | null;
  caller_phone?: string | null;
  caller_age?: number | null;
  caller_gender?: string | null;
  consultant_id: string;
  consultant_name: string;
  department: Department;
  scheduled_start: string;
  duration_minutes: number;
  status: AppointmentStatus;
  visit_type: VisitType;
  visit_id?: string | null;
  reason?: string | null;
  referred_by?: string | null;
  booked_by_name: string;
  cancellation_reason?: string | null;
}

export interface BoardRow {
  /** Null for a walk-in: there is no booking behind it. */
  id?: string | null;
  kind: "appointment" | "walk_in";
  visit_id?: string | null;
  visit_number?: string | null;
  token_number?: number | null;
  patient_id?: string | null;
  patient_name: string;
  /** Empty until the caller is registered. */
  uhid: string;
  registered: boolean;
  phone_number?: string | null;
  consultant_name: string;
  department: Department;
  scheduled_start?: string | null;
  duration_minutes?: number | null;
  visit_type: VisitType;
  reason?: string | null;
  status: AppointmentStatus;
}

export interface Board {
  date: string;
  counts: Record<AppointmentStatus, number>;
  rows: BoardRow[];
}

export interface Consultant {
  id: string;
  full_name: string;
  department: Department;
  qualification?: string | null;
  registration_number?: string | null;
  phone_number?: string | null;
  user_id?: string | null;
  appointment_minutes: number;
  opd_start_time: string;
  opd_end_time: string;
  opd_days: string;
  free_follow_up_days: number;
  consultation_service_code?: string | null;
  first_consultation_free?: boolean;
  /** Set on the Accounts screen only; read-only everywhere else. */
  payout_share_percent: number;
  payout_categories?: string[];
  notes?: string | null;
  is_active: boolean;
}
