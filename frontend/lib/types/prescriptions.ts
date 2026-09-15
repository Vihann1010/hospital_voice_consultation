/** Contracts for the prescription module. */
import type { Department } from "@/lib/types/core";

export type PrescriptionStatus = "draft" | "issued" | "cancelled";
export type DeliveryChannel = "whatsapp" | "sms" | "email";
export type DeliveryStatus =
  | "pending" | "sending" | "sent" | "delivered" | "read" | "failed" | "cancelled";

export interface FormularyMedicine {
  code: string;
  name: string;
  ingredients: string[];
  form: string;
  strengths: string[];
  default_frequency?: string | null;
  default_duration?: string | null;
  default_timing?: string | null;
  category: string;
  note?: string | null;
}

export interface MedicineTemplate {
  disease_name: string;
  department: Department;
  note: string;
  medicines: FormularyMedicine[];
}

export interface PrescriptionAssist {
  diagnosis: string;
  medicines: MedicineRow[];
  templates: string[];
  intake_context: {
    chief_complaint?: string;
    clinical_findings?: string;
    investigations: string[];
    allergies: string[];
    current_medicines: { name: string; dose_or_frequency?: string }[];
  };
  note: string;
}

/** One editable row in the composer. */
export interface MedicineRow {
  key: string;
  name: string;
  formulary_code?: string | null;
  generic?: string | null;
  form?: string | null;
  strength?: string | null;
  dosage?: string | null;
  frequency_code?: string | null;
  frequency_text?: string | null;
  duration?: string | null;
  timing?: string | null;
  route?: string | null;
  instructions?: string | null;
  source: "dictated" | "manual" | "catalog" | "template";
  /** Set when the duration came from the follow-up interval rather than the
   *  doctor typing it, so a later change to the interval may safely update it. */
  durationFromFollowUp?: boolean;
  confidence?: number;
  unmatched?: boolean;
  substituted?: boolean;
  warnings?: string[];
}

export interface DictatedMedicine {
  raw_text: string;
  name: string;
  formulary_code?: string | null;
  generic?: string | null;
  form?: string | null;
  strength?: string | null;
  dosage?: string | null;
  frequency_code?: string | null;
  frequency_text?: string | null;
  duration?: string | null;
  timing?: string | null;
  route?: string | null;
  instructions?: string | null;
  confidence: number;
  unmatched: boolean;
  substituted: boolean;
  warnings: string[];
}

export interface SafetyAlert {
  kind: "interaction" | "duplicate" | "allergy" | "pregnancy" | "formulary";
  severity: "info" | "caution" | "serious";
  medicines: string[];
  description: string;
  suggested_action?: string | null;
  detected_by: "rule" | "ai";
}

export interface SafetyCheckResponse {
  alerts: SafetyAlert[];
  blocking: number;
  known_allergies: string[];
}

export interface Delivery {
  id: string;
  channel: DeliveryChannel;
  provider: string;
  recipient: string;
  status: DeliveryStatus;
  attempts: number;
  provider_message_id?: string | null;
  error_detail?: string | null;
  last_attempt_at?: string | null;
  next_retry_at?: string | null;
  delivered_at?: string | null;
  is_final: boolean;
  requested_by_name: string;
  created_at: string;
}

export interface PrescriptionMedicine {
  id: string;
  position: number;
  formulary_code?: string | null;
  name: string;
  generic?: string | null;
  form?: string | null;
  strength?: string | null;
  dosage?: string | null;
  frequency_code?: string | null;
  frequency_text?: string | null;
  duration?: string | null;
  timing?: string | null;
  route?: string | null;
  instructions?: string | null;
  source: string;
}

export interface Prescription {
  id: string;
  prescription_number: string;
  patient_id: string;
  consultation_id?: string | null;
  department: Department;
  status: PrescriptionStatus;
  doctor_name: string;
  doctor_qualification?: string | null;
  doctor_registration?: string | null;
  diagnosis?: string | null;
  cause?: string | null;
  chief_complaint?: string | null;
  clinical_findings?: string | null;
  investigations_advised?: string[];
  general_instructions?: string | null;
  follow_up_notes?: string | null;
  follow_up_date?: string | null;
  dictation_transcript?: string | null;
  pdf_filename?: string | null;
  pdf_generated_at?: string | null;
  issued_at?: string | null;
  created_at: string;
  medicines: PrescriptionMedicine[];
  deliveries: Delivery[];
}

export const FREQUENCY_OPTIONS: { code: string; label: string }[] = [
  { code: "OD", label: "Once a day" },
  { code: "BD", label: "Twice a day" },
  { code: "TDS", label: "Three times a day" },
  { code: "QID", label: "Four times a day" },
  { code: "HS", label: "At bedtime" },
  { code: "SOS", label: "Only when needed" },
  { code: "STAT", label: "Single dose now" },
  { code: "WEEKLY", label: "Once a week" },
  { code: "ALT", label: "On alternate days" },
];

/**
 * Follow-up intervals offered to the doctor.
 *
 * Choosing one sets every medicine's duration to the interval plus a day, so
 * the patient does not run out the morning they are due back — a prescription
 * that ends the night before the review is a phone call the clinic does not
 * need.
 */
export const FOLLOW_UP_OPTIONS: { days: number; label: string }[] = [
  { days: 3, label: "After 3 days" },
  { days: 5, label: "After 5 days" },
  { days: 7, label: "After 7 days" },
  { days: 10, label: "After 10 days" },
  { days: 14, label: "After 14 days" },
];

/** Medicines are dispensed for one day longer than the follow-up interval. */
export function durationForFollowUp(days: number): string {
  const total = days + 1;
  return `${total} days`;
}

export const TIMING_OPTIONS = [
  "Before breakfast", "After breakfast", "Before food", "After food",
  "On an empty stomach", "At bedtime", "In the morning", "In the evening",
  "Per vaginam", "Apply locally",
];

export const DELIVERY_LABEL: Record<DeliveryStatus, string> = {
  pending: "Queued",
  sending: "Sending",
  sent: "Sent",
  delivered: "Delivered",
  read: "Read",
  failed: "Failed",
  cancelled: "Cancelled",
};
