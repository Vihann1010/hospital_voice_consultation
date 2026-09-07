/** IPD contracts. Amounts are integer paise, matching the backend. */
import type { Department } from "@/lib/types";

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
