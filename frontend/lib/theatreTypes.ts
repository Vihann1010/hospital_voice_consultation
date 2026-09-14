/** The operation theatre: bookings, theatre times, and the lists behind them. */
import type { Department } from "@/lib/types";

export type SurgeryStatus = "scheduled" | "in_theatre" | "completed" | "cancelled";

export type Milestone =
  | "wheel_in_at"
  | "anaesthesia_start_at"
  | "incision_at"
  | "closure_at"
  | "wheel_out_at";

export type TheatreDocumentStatus = "missing" | "draft" | "signed";

export interface TheatreDocument {
  document_type: string;
  label: string;
  authority: "doctor" | "nursing";
  status: TheatreDocumentStatus;
}

export interface Surgery {
  id: string;
  ot_number: string;
  status: SurgeryStatus;
  patient: { id: string; name: string; uhid: string | null; age: number; gender: string } | null;
  admission_id: string | null;
  ip_number: string | null;
  allergies: string[];
  department: Department;
  operation_id: string | null;
  operation_name: string;
  laterality: string;
  diagnosis: string | null;
  surgeon_consultant_id: string | null;
  surgeon_name: string;
  assistants: string[];
  anaesthetist_name: string | null;
  anaesthesia_type: string | null;
  room_id: string | null;
  room_name: string | null;
  scheduled_at: string;
  expected_minutes: number;
  priority: "elective" | "emergency";
  wheel_in_at: string | null;
  anaesthesia_start_at: string | null;
  incision_at: string | null;
  closure_at: string | null;
  wheel_out_at: string | null;
  durations: {
    theatre_minutes: number | null;
    surgery_minutes: number | null;
    anaesthesia_minutes: number | null;
  };
  cancel_reason: string | null;
  notes: string | null;
  booked_by_name: string | null;
  charge_reference: string | null;
  documents: TheatreDocument[];
  created_at: string;
  /** Only on a theatre-time response: why a completed case was not billed. */
  charge_note?: string | null;
}

export interface TheatreOptions {
  laterality: string[];
  anaesthesia_types: string[];
  priorities: string[];
  grades: string[];
  milestones: { key: Milestone; label: string }[];
}

export interface TheatreRoom {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
  notes: string | null;
}

export interface Operation {
  id: string;
  code: string;
  name: string;
  department: Department | null;
  grade: string | null;
  default_minutes: number;
  service_code: string | null;
  is_active: boolean;
  notes: string | null;
}

export const MILESTONES: { key: Milestone; label: string }[] = [
  { key: "wheel_in_at", label: "Wheeled in" },
  { key: "anaesthesia_start_at", label: "Anaesthesia started" },
  { key: "incision_at", label: "Incision" },
  { key: "closure_at", label: "Closure" },
  { key: "wheel_out_at", label: "Wheeled out" },
];

export const SURGERY_STATUS_LABEL: Record<SurgeryStatus, string> = {
  scheduled: "Scheduled",
  in_theatre: "In theatre",
  completed: "Completed",
  cancelled: "Cancelled",
};

export const SURGERY_STATUS_VARIANT: Record<
  SurgeryStatus,
  "secondary" | "warning" | "success" | "outline"
> = {
  scheduled: "secondary",
  in_theatre: "warning",
  completed: "success",
  cancelled: "outline",
};

export const PRE_OP_CHECKLIST = "ot_pre_op_checklist";

/** Booking and cancelling is the doctor's; recording times is shared with nurses. */
export const canSchedule = (role?: string) => role === "admin" || role === "doctor";
export const canRecord = (role?: string) =>
  role === "admin" || role === "doctor" || role === "nurse";
/** The operation list carries price codes, so it is master data. */
export const canMaintainTheatre = (role?: string) => role === "admin" || role === "manager";

const HOSPITAL_ZONE = "Asia/Kolkata";

/**
 * A moment as the value of a datetime-local input, in hospital time.
 *
 * A theatre list is in Kanpur time wherever it is read from; a browser's own
 * timezone must not move a 9 o'clock case.
 */
export function toHospitalInput(iso: string | Date): string {
  const moment = typeof iso === "string" ? new Date(iso) : iso;
  const date = new Intl.DateTimeFormat("en-CA", { timeZone: HOSPITAL_ZONE }).format(moment);
  const time = new Intl.DateTimeFormat("en-GB", {
    timeZone: HOSPITAL_ZONE,
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(moment);
  return `${date}T${time}`;
}

/** A datetime-local value, read as hospital time, as the ISO string the API expects. */
export function fromHospitalInput(value: string): string {
  return new Date(`${value}:00+05:30`).toISOString();
}

export function minutesLabel(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "—";
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours} h ${minutes % 60} min` : `${minutes} min`;
}

export function checklistSigned(surgery: Surgery): boolean {
  return surgery.documents.some(
    (item) => item.document_type === PRE_OP_CHECKLIST && item.status === "signed"
  );
}
