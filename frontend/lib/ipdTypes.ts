/** IPD contracts. Amounts are integer paise, matching the backend. */
import type { Department } from "@/lib/types";
import type { SafetyAlert } from "@/lib/prescriptionTypes";

export type WardType =
  | "general" | "semi_private" | "private" | "deluxe" | "icu" | "hdu"
  | "nicu" | "labour" | "post_operative" | "day_care";
export type BedStatus = "vacant" | "occupied" | "cleaning" | "blocked" | "maintenance";
export type AdmissionStatus =
  | "admitted" | "discharge_initiated" | "discharged" | "cancelled";
export type DischargeType =
  | "routine" | "against_medical_advice" | "transferred_out" | "absconded" | "death";
export type ChargeCategory =
  | "bed" | "nursing" | "doctor_visit" | "procedure" | "investigation"
  | "medicine" | "consumable" | "oxygen" | "other";
export type NewsRisk = "none" | "low" | "medium" | "high" | "critical";

export interface BedOccupant {
  admission_id: string;
  ip_number: string;
  patient_name: string;
  uhid: string | null;
  age: number;
  gender: string;
  admitted_at: string;
  doctor: string;
  diagnosis: string | null;
  on_leave?: boolean;
  expected_return_on?: string | null;
}

export interface BedCell {
  id: string;
  label: string;
  status: BedStatus;
  rate_paise: number;
  oxygen: boolean;
  occupant: BedOccupant | null;
}

export interface WardBoard {
  id: string;
  code: string;
  name: string;
  ward_type: WardType;
  department: Department | null;
  daily_rate_paise: number;
  total_beds: number;
  occupied: number;
  vacant: number;
  beds: BedCell[];
}

export interface Census {
  on: string;
  total_beds: number;
  occupied: number;
  vacant: number;
  cleaning: number;
  out_of_service: number;
  occupancy_percent: number;
  current_inpatients: number;
  admissions_today: number;
  discharges_today: number;
}

export interface News2Result {
  total: number;
  risk: NewsRisk;
  response: string;
  monitoring: string;
  red_score: boolean;
  missing: string[];
}

export interface VitalsRecord {
  id: string;
  recorded_at: string;
  recorded_by_name: string;
  respiratory_rate: number | null;
  spo2_percent: number | null;
  on_oxygen: boolean;
  systolic_bp: number | null;
  diastolic_bp: number | null;
  pulse: number | null;
  temperature_c: number | null;
  consciousness: string | null;
  pain_score: number | null;
  news2_score: number | null;
  news2_risk: NewsRisk | null;
}

export interface DeterioratingPatient {
  admission_id: string;
  ip_number: string;
  patient_name: string;
  uhid: string | null;
  ward: string;
  bed: string;
  news2_score: number;
  risk: NewsRisk;
  recorded_at: string;
  response: string;
}

export interface RunningBill {
  admission_id: string;
  ip_number: string;
  by_category: Record<string, { count: number; total_paise: number }>;
  total_paise: number;
  advance_paid_paise: number;
  balance_paise: number;
  days_so_far: number;
}

export type MedicationStatus = "active" | "completed" | "stopped" | "held";

export interface AdmissionSummary {
  id: string;
  ip_number: string;
  patient_id: string;
  department: Department;
  admitting_doctor_name: string;
  admission_type: string;
  status: AdmissionStatus;
  admitted_at: string;
  discharged_at?: string | null;
  provisional_diagnosis?: string | null;
  final_diagnosis?: string | null;
  reason_for_admission?: string | null;
  allergies?: string[] | null;
  attendant_name?: string | null;
  attendant_phone?: string | null;
  advance_paid_paise: number;
  discharge_type?: DischargeType | null;
  readmission_of_id?: string | null;
  days_since_last_discharge?: number | null;
  created_at: string;
}

export interface MedicationOrder {
  id: string;
  drug_name: string;
  generic_name?: string | null;
  strength?: string | null;
  dose: string;
  route: string;
  frequency_code: string;
  schedule_times?: string[] | null;
  status: MedicationStatus;
  started_at: string;
  stopped_at?: string | null;
  is_stat: boolean;
  is_sos: boolean;
  instructions?: string | null;
}

export interface WardNote {
  id?: string;
  note_type: string;
  author_name: string;
  content: string;
  created_at: string;
  ai_generated?: boolean;
}

/** The whole bedside chart, as `GET /ipd/admissions/{id}` returns it. */
export interface AdmissionChart {
  admission: AdmissionSummary;
  patient: {
    id: string;
    uhid: string | null;
    name: string;
    age: number;
    gender: string;
    phone_number: string;
    blood_group?: string | null;
  } | null;
  current_bed: { ward: string; bed: string; since: string } | null;
  occupancies: { ward: string; bed: string; from: string; to: string | null; reason?: string | null }[];
  vitals: VitalsRecord[];
  medications: MedicationOrder[];
  notes: WardNote[];
  bill: RunningBill;
  leaves?: AdmissionLeave[];
  readmission_of?: {
    id: string;
    ip_number: string;
    discharged_at: string | null;
    final_diagnosis: string | null;
    days_since: number | null;
  } | null;
}

export interface AdmissionLeave {
  id: string;
  started_at: string;
  expected_return_on: string | null;
  reason: string;
  bed_retained: boolean;
  released_bed: string | null;
  started_by_name: string;
  returned_at: string | null;
  returned_by_name: string | null;
  return_note: string | null;
}

export interface RoomChargeRun {
  id: string;
  run_on: string;
  status: "running" | "done" | "partial" | "skipped" | "failed";
  started_at: string;
  finished_at: string | null;
  summary: { admissions?: number; charges_posted?: number; failed?: { ip_number: string; error: string }[] };
  error: string | null;
  triggered_by: string;
}

export interface RoomChargeRuns {
  run_at: string;
  enabled: boolean;
  runs: RoomChargeRun[];
}

export const DISCHARGE_TYPE_LABEL: Record<DischargeType, string> = {
  routine: "Routine — going home",
  transferred_out: "Transferred to another hospital",
  against_medical_advice: "Left against medical advice",
  absconded: "Absconded",
  death: "Death",
};

export type DoseState = "given" | "omitted" | "overdue" | "due" | "upcoming" | "on_leave";

export interface ChartDose {
  id: string;
  due_at: string;
  state: DoseState;
  given_at?: string | null;
  given_by_name: string;
  omission_reason?: string | null;
  notes?: string | null;
  can_sign: boolean;
}

export interface ChartOrder {
  id: string;
  drug_name: string;
  generic_name?: string | null;
  strength?: string | null;
  dose: string;
  route: string;
  frequency_code: string;
  schedule_times: string[];
  status: MedicationStatus;
  started_at: string;
  stopped_at?: string | null;
  stop_reason?: string | null;
  is_stat: boolean;
  is_sos: boolean;
  instructions?: string | null;
  ordered_by_name: string;
  last_given_at?: string | null;
  doses: ChartDose[];
}

/** One day of the drug chart, as `GET /ipd/admissions/{id}/drug-chart` returns it. */
export interface DrugChart {
  /** The patient is away on leave now. */
  on_leave?: boolean;
  on: string;
  now: string;
  allergies: string[];
  frequencies: Record<string, string[]>;
  routes: string[];
  orders: ChartOrder[];
  summary: { due: number; overdue: number; given: number; omitted: number };
}

export interface DrugCheck {
  alerts: SafetyAlert[];
  blocking: number;
  allergies: string[];
}

/** Colour and label for a NEWS2 band.
 *
 *  Deliberately not a gradient: a nurse scanning a ward board needs the
 *  critical patients to be unmistakable, not slightly redder than the rest.
 */
export const NEWS_BANDS: Record<NewsRisk, { label: string; className: string }> = {
  none:     { label: "Stable",   className: "bg-mint text-pine" },
  low:      { label: "Low",      className: "bg-mint text-pine" },
  medium:   { label: "Watch",    className: "bg-marigold/20 text-marigold-deep" },
  high:     { label: "Urgent",   className: "bg-clay/15 text-clay" },
  critical: { label: "CRITICAL", className: "bg-clay text-white" },
};

export const BED_STATUS_STYLE: Record<BedStatus, string> = {
  vacant: "border-pine/15 bg-white hover:border-pine/40",
  occupied: "border-pine/30 bg-mint",
  cleaning: "border-marigold/40 bg-marigold/[0.07]",
  blocked: "border-border bg-paper opacity-60",
  maintenance: "border-border bg-paper opacity-60",
};

export const WARD_TYPE_LABEL: Record<WardType, string> = {
  general: "General", semi_private: "Semi-private", private: "Private",
  deluxe: "Deluxe", icu: "ICU", hdu: "HDU", nicu: "NICU",
  labour: "Labour", post_operative: "Post-op", day_care: "Day care",
};

/** Days between admission and now, counting the day of admission. */
export function dayOfStay(admittedAt: string): number {
  const start = new Date(admittedAt);
  const now = new Date();
  const days = Math.floor(
    (now.setHours(0, 0, 0, 0) - start.setHours(0, 0, 0, 0)) / 86400000
  );
  return days + 1;
}
