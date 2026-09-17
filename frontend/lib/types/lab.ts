/** The in-house laboratory, mirroring app/api/v1/routes/lab.py. */

export type ResultType = "numeric" | "text" | "choice" | "heading";
export type LabFlag = "normal" | "low" | "high" | "critical_low" | "critical_high" | "abnormal" | null;
export type LabItemStatus = "registered" | "collected" | "entered" | "verified" | "cancelled";
export type LabRequestStatus =
  | "registered"
  | "collected"
  | "in_progress"
  | "partly_verified"
  | "verified"
  | "cancelled";
export type LabBilling = "invoice" | "ipd" | "unbilled";
export type LabPriority = "routine" | "urgent" | "stat";
export type MasterKind = "unit" | "method" | "specimen" | "antibiotic" | "organism" | "group";

export interface LabRange {
  sex: "male" | "female" | null;
  min_age: number;
  max_age: number;
  low: number | null;
  high: number | null;
  critical_low: number | null;
  critical_high: number | null;
}

export interface LabParameter {
  id: string;
  position: number;
  name: string;
  analyte_key: string | null;
  aliases: string[];
  result_type: ResultType;
  unit: string | null;
  method: string | null;
  choices: string[];
  normal_values: string[];
  ranges: LabRange[];
  range_text: string | null;
  print_default: boolean;
  is_active: boolean;
  /** The range that applies to this patient, for the entry screen. */
  range_preview?: string | null;
}

export interface LabTest {
  id: string;
  code: string;
  name: string;
  group_name: string;
  specimen: string | null;
  service_code: string | null;
  catalog_code: string | null;
  is_culture: boolean;
  turnaround_hours: number;
  interpretation: string | null;
  position: number;
  is_active: boolean;
  notes: string | null;
  ranges_reviewed_at: string | null;
  ranges_reviewed_by_name: string | null;
  parameters: LabParameter[];
}

export interface LabMaster {
  id: string;
  kind: MasterKind;
  name: string;
  code: string | null;
  category: string | null;
  position: number;
  is_active: boolean;
}

export interface LabOptions {
  groups: string[];
  master_kinds: MasterKind[];
  result_types: ResultType[];
  susceptibility: { key: "S" | "I" | "R"; label: string }[];
  billing_modes: LabBilling[];
  priorities: LabPriority[];
}

export interface LabResultRow {
  parameter_id: string;
  name: string;
  result_type: ResultType;
  unit: string | null;
  method: string | null;
  value: string | null;
  flag: LabFlag;
  reference_text: string | null;
  note: string | null;
  print: boolean;
}

export interface CultureAntibiotic {
  name: string;
  result: "S" | "I" | "R" | "";
  value: string | null;
}

export interface CultureIsolate {
  organism: string;
  colony_count: string | null;
  antibiotics: CultureAntibiotic[];
}

export interface CultureResult {
  specimen: string | null;
  growth: "growth" | "no_growth" | null;
  incubation: string | null;
  isolates: CultureIsolate[];
  comment: string | null;
}

export interface LabItem {
  id: string;
  test_id: string | null;
  order_item_id: string | null;
  code: string;
  name: string;
  group_name: string;
  specimen: string | null;
  is_culture: boolean;
  unit_rate_paise: number;
  status: LabItemStatus;
  results: LabResultRow[];
  culture: CultureResult | null;
  remarks: string | null;
  critical_note: string | null;
  entered_at: string | null;
  entered_by_name: string | null;
  verified_at: string | null;
  verified_by_name: string | null;
  verifier_qualification: string | null;
  verifier_registration: string | null;
  version: number;
  amendments: { version: number; reason: string; reopened_by_name: string; reopened_at: string }[];
  cancelled_at: string | null;
  cancel_reason: string | null;
  /** Entry form lines, present while the test is still open. */
  parameters: LabParameter[] | null;
  /** False when the pathologist has not reviewed this test's ranges yet. */
  ranges_reviewed: boolean | null;
}

export interface LabPatient {
  id: string;
  name: string;
  uhid: string | null;
  age: number;
  gender: "male" | "female" | "other";
  phone_number: string;
}

export interface LabRequest {
  id: string;
  lab_number: string;
  status: LabRequestStatus;
  billing: LabBilling;
  priority: LabPriority;
  referred_by: string | null;
  consultant_id: string | null;
  clinical_notes: string | null;
  consultation_id: string | null;
  order_id: string | null;
  registered_by_name: string;
  created_at: string;
  sample_collected_at: string | null;
  sample_collected_by_name: string | null;
  cancelled_at: string | null;
  cancel_reason: string | null;
  patient: LabPatient;
  admission: { id: string; ip_number: string; status: string } | null;
  invoice: {
    id: string;
    invoice_number: string;
    status: string;
    total_paise: number;
    paid_paise: number;
    balance_paise: number;
  } | null;
  items: LabItem[];
  printable: boolean;
  /** Present after a cancellation. */
  refund_due_paise?: number;
  notes?: string[];
}

export interface LabRequestSummary {
  id: string;
  lab_number: string;
  status: LabRequestStatus;
  billing: LabBilling;
  priority: LabPriority;
  referred_by: string | null;
  created_at: string;
  sample_collected_at: string | null;
  hours_waiting: number;
  patient: LabPatient;
  tests: { id: string; name: string; status: LabItemStatus }[];
}

export interface PendingLabOrder {
  order_id: string;
  consultation_id: string | null;
  ordered_at: string;
  ordered_by_name: string;
  priority: string;
  clinical_notes: string | null;
  provisional_diagnosis: string | null;
  patient: { id: string; name: string; uhid: string | null; age: number; gender: string };
  admission: { id: string; ip_number: string } | null;
  items: {
    item_id: string;
    code: string;
    name: string;
    category: string;
    test: { id: string; code: string; name: string; priced: boolean } | null;
  }[];
}

export interface PrintoutReading {
  unclear: boolean;
  message: string | null;
  suggestions: { parameter_id: string; name: string; value: string; raw_line: string }[];
  conflicts: string[];
  unit_mismatches: string[];
  unmatched_lines: string[];
  unmatched_count: number;
}

export interface PatientLabResult extends LabItem {
  request_id: string;
  lab_number: string;
  registered_at: string;
  referred_by: string | null;
}

export const FLAG_MARK: Record<string, string> = {
  low: "L",
  high: "H",
  critical_low: "LL",
  critical_high: "HH",
  abnormal: "*",
};

export const REQUEST_STATUS_LABEL: Record<LabRequestStatus, string> = {
  registered: "Registered",
  collected: "Sample collected",
  in_progress: "In progress",
  partly_verified: "Partly verified",
  verified: "Verified",
  cancelled: "Cancelled",
};

export const ITEM_STATUS_LABEL: Record<LabItemStatus, string> = {
  registered: "Awaiting sample",
  collected: "Sample collected",
  entered: "Results entered",
  verified: "Verified",
  cancelled: "Cancelled",
};

export const BILLING_LABEL: Record<LabBilling, string> = {
  invoice: "Counter bill",
  ipd: "Admission",
  unbilled: "Not billed",
};

export const isAbnormal = (flag: LabFlag) =>
  flag === "low" || flag === "high" || flag === "critical_low" || flag === "critical_high" || flag === "abnormal";

export const isCritical = (flag: LabFlag) => flag === "critical_low" || flag === "critical_high";

/** Who may do what on the lab screens; the server enforces the same. */
export const canRegisterLab = (role?: string) =>
  ["admin", "doctor", "supervisor", "reception", "nurse", "lab"].includes(role ?? "");
export const canEnterLab = (role?: string) => ["admin", "doctor", "lab"].includes(role ?? "");
export const canVerifyLab = (role?: string) => ["admin", "doctor"].includes(role ?? "");
export const canEditLabTests = (role?: string) => ["admin", "doctor"].includes(role ?? "");
export const canBillAtCounter = (role?: string) =>
  ["admin", "doctor", "supervisor", "reception"].includes(role ?? "");
