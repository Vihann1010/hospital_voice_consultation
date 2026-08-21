/** Shared contracts mirroring the backend Pydantic schemas. */

export type Department = "orthopedics" | "gynecology";
export type Gender = "male" | "female" | "other";
export type ConsultationStatus = "in_progress" | "completed" | "abandoned";
export type RiskLevel = "low" | "moderate" | "high" | "critical";
export type TriagePriority = "routine" | "soon" | "urgent" | "immediate";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "admin" | "doctor" | "staff";
  department: Department | null;
  is_active: boolean;
}

export interface Patient {
  id: string;
  name: string;
  age: number;
  gender: Gender;
  phone_number: string;
  created_at: string;
}

export interface PatientListItem extends Patient {
  visit_count: number;
}

export interface ConversationTurn {
  id: string;
  role: "patient" | "assistant";
  content: string;
  sequence: number;
  interrupted: boolean;
  created_at: string;
}

// ---- Clinical dossier (schema_version 2.0) --------------------------------
export interface MedicalRecord {
  chief_complaint?: string | null;
  symptoms?: { name: string; details?: string | null }[];
  pain?: {
    location?: string | null;
    character?: string | null;
    score_out_of_10?: number | null;
    aggravating_factors?: string | null;
    relieving_factors?: string | null;
  };
  duration?: string | null;
  medical_history?: string[];
  current_medicines?: { name: string; dose_or_frequency?: string | null }[];
  previous_surgeries?: { name: string; year_or_when?: string | null }[];
  allergies?: string[];
  weight_kg?: number | null;
  height_cm?: number | null;
  department_specific?: Record<string, unknown>;
  red_flags?: string[];
  summary_for_doctor?: string | null;
}

export interface RiskAssessment {
  overall_risk: RiskLevel;
  emergency: boolean;
  red_flags: { flag: string; rationale?: string | null; severity: RiskLevel }[];
  recommended_action?: string | null;
  triage_priority: TriagePriority;
}

export interface ClinicalSummary {
  one_liner?: string | null;
  history_of_present_illness?: string | null;
  pertinent_positives?: string[];
  pertinent_negatives?: string[];
  relevant_background?: string[];
  summary_for_doctor?: string | null;
}

export interface DifferentialDiagnosis {
  differentials: {
    condition: string;
    likelihood: "high" | "moderate" | "low";
    supporting_features?: string[];
    features_against?: string[];
    would_change_with?: string | null;
  }[];
  reasoning_note?: string | null;
  disclaimer?: string;
}

export interface InvestigationPlan {
  investigations: {
    test: string;
    priority: "immediate" | "urgent" | "routine";
    rationale?: string | null;
    fasting_or_prep_required?: string | null;
  }[];
  already_done_to_review?: string[];
  note_for_doctor?: string | null;
}

export interface PatientEducation {
  language: "en" | "hi" | "mixed";
  understanding_your_visit?: string | null;
  what_to_expect_at_hospital?: string | null;
  general_self_care?: string[];
  warning_signs_return_immediately?: string[];
  questions_to_ask_your_doctor?: string[];
  disclaimer?: string;
}

export interface ClinicalDossier {
  schema_version?: string;
  medical_json?: MedicalRecord;
  risk_assessment?: RiskAssessment;
  clinical_summary?: ClinicalSummary;
  differential_diagnosis?: DifferentialDiagnosis;
  investigations?: InvestigationPlan;
  patient_education?: PatientEducation;
  conversation_meta?: Record<string, unknown>;
  pipeline_errors?: string[];
  reviewed_at?: string | null;
  reviewed_by?: { id: string; name: string } | null;
  copilot?: CopilotBriefing | null;
}

// ---- Copilot --------------------------------------------------------------
export interface MedicationAlert {
  kind: "interaction" | "allergy" | "duplicate";
  severity: "info" | "caution" | "serious";
  medicines_involved: string[];
  description: string;
  suggested_action?: string | null;
  detected_by: "rule" | "ai";
}

export interface FollowUpQuestion {
  question: string;
  why_it_matters?: string | null;
  targets?: string | null;
}

export interface ReferralSuggestion {
  specialty: string;
  urgency: "routine" | "soon" | "urgent";
  reason: string;
}

export interface CopilotDecision {
  decision: "accepted" | "dismissed" | "pending";
  note?: string | null;
  doctor_name?: string | null;
  at?: string | null;
}

export interface CopilotBriefing {
  schema_version?: string;
  generated_at?: string | null;
  medication_alerts: MedicationAlert[];
  follow_up_questions: FollowUpQuestion[];
  referrals: ReferralSuggestion[];
  notes?: string | null;
  errors?: string[];
  disclaimer?: string;
  decisions?: Record<string, CopilotDecision>;
}

// ---- Consultations --------------------------------------------------------
export interface Consultation {
  id: string;
  patient_id: string;
  department: Department;
  status: ConsultationStatus;
  medical_json: ClinicalDossier | null;
  transcript: string | null;
  started_at: string;
  ended_at: string | null;
}

export interface ConsultationListItem extends Consultation {
  patient: Patient | null;
  has_recording: boolean;
  reviewed_at: string | null;
}

export interface ConsultationDetail extends Consultation {
  patient: Patient;
  turns: ConversationTurn[];
  has_recording: boolean;
}

export interface ConsultationStats {
  in_progress: number;
  completed: number;
  abandoned: number;
  last_24h: number;
  waiting: number;
}

export interface PatientVisit {
  consultation_id: string;
  department: Department;
  status: ConsultationStatus;
  started_at: string;
  ended_at: string | null;
  chief_complaint: string | null;
  overall_risk: RiskLevel | null;
  one_liner: string | null;
  has_recording: boolean;
}

export interface PatientHistory {
  patient: Patient;
  summary: {
    current_medicines: { name: string; dose_or_frequency?: string | null }[];
    allergies: string[];
    conditions: string[];
    previous_surgeries: { name: string; year_or_when?: string | null }[];
    total_visits: number;
  };
  visits: PatientVisit[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
}
