/** TPA and insurance claims — mirrors app/api/v1/routes/insurance.py. Money is integer paise. */

export type ClaimStatus =
  | "draft"
  | "pre_auth_requested"
  | "pre_auth_approved"
  | "pre_auth_rejected"
  | "submitted"
  | "queried"
  | "approved"
  | "partially_approved"
  | "rejected"
  | "settled";

export interface ClaimPolicy {
  id: string;
  patient_id: string;
  payer_type: string;
  insurer_name: string;
  tpa_name: string | null;
  policy_number: string;
  member_id: string | null;
  scheme_name: string | null;
  valid_from: string | null;
  valid_to: string | null;
  sum_insured_paise: number | null;
  is_active: boolean;
  organisation_id: string | null;
  organisation_name: string | null;
}

export interface ClaimSettlement {
  id: string;
  received_on: string;
  received_paise: number;
  tds_paise: number;
  deduction_paise: number;
  deduction_reason: string | null;
  mode: string;
  reference: string | null;
  notes: string | null;
  created_by_name: string;
  created_at: string;
  cancelled_at: string | null;
  cancelled_by_name: string | null;
  cancel_reason: string | null;
}

export interface ClaimHistoryEntry {
  at: string;
  status: ClaimStatus;
  by: string;
  note?: string;
  [amount: string]: unknown;
}

export interface Claim {
  id: string;
  claim_number: string;
  status: ClaimStatus;
  status_label: string;
  next_statuses: ClaimStatus[];
  patient: { id: string; name: string; uhid: string | null };
  policy: ClaimPolicy;
  payer_name: string;
  organisation_id: string | null;
  admission: { id: string; ip_number: string; status: string } | null;
  invoice: {
    id: string;
    invoice_number: string;
    status: string;
    total_paise: number;
    paid_paise: number;
    balance_paise: number;
  } | null;
  external_reference: string | null;
  pre_auth_requested_paise: number;
  pre_auth_approved_paise: number;
  claimed_paise: number;
  approved_paise: number;
  booked_paise: number;
  booked_on: string | null;
  booking_receipt_number: string | null;
  received_paise: number;
  tds_paise: number;
  deducted_paise: number;
  outstanding_paise: number;
  patient_liability_paise: number;
  diagnosis: string | null;
  treatment_summary: string | null;
  rejection_reason: string | null;
  query_detail: string | null;
  submitted_at: string | null;
  decided_at: string | null;
  settled_at: string | null;
  created_at: string;
  created_by_name: string;
  age_days: number;
  can_book: boolean;
  /** Things that do not add up. Shown as they are; never guessed at. */
  attention: string[];
}

export interface ClaimDetail extends Claim {
  history: ClaimHistoryEntry[];
  settlements: ClaimSettlement[];
}

export interface InsuranceOptions {
  statuses: { value: ClaimStatus; label: string; next: ClaimStatus[] }[];
  payers: { id: string; code: string; name: string; payer_type: string }[];
  payer_types: string[];
  settlement_modes: string[];
}

export interface PatientInsurance {
  patient: { id: string; name: string; uhid: string | null };
  policies: ClaimPolicy[];
  admissions: { id: string; ip_number: string; status: string; admitted_at: string; final_invoice_id: string | null }[];
  bills: {
    id: string;
    invoice_number: string;
    issued_at: string;
    status: string;
    total_paise: number;
    paid_paise: number;
    balance_paise: number;
    admission_ip_number: string | null;
  }[];
  claims: Claim[];
}

export interface OutstandingItem {
  claim_id: string;
  claim_number: string;
  payer_name: string;
  patient_name: string;
  uhid: string;
  status: ClaimStatus;
  external_reference: string;
  booked_on: string;
  age_days: number;
  bucket: string;
  booked_paise: number;
  settled_paise: number;
  outstanding_paise: number;
}

export interface PayerOutstanding {
  as_of: string;
  buckets: string[];
  items: OutstandingItem[];
  payers: (Record<string, number | string> & { payer_name: string; claims: number; outstanding_paise: number })[];
  total_paise: number;
}

export const CLAIM_STATUS_LABEL: Record<ClaimStatus, string> = {
  draft: "Draft",
  pre_auth_requested: "Pre-authorisation requested",
  pre_auth_approved: "Pre-authorisation approved",
  pre_auth_rejected: "Pre-authorisation rejected",
  submitted: "Claim submitted",
  queried: "Query raised",
  approved: "Approved",
  partially_approved: "Partially approved",
  rejected: "Rejected",
  settled: "Settled",
};

export const PAYER_TYPE_LABEL: Record<string, string> = {
  insurance: "Insurance company",
  tpa: "TPA",
  corporate: "Employer",
  government_scheme: "Government scheme",
};

export const SETTLEMENT_MODE_LABEL: Record<string, string> = {
  net_banking: "Bank transfer",
  cheque: "Cheque",
  upi: "UPI",
};

/** Colour for a claim's stage: green when the payer said yes, red when they said no. */
export function statusClass(status: ClaimStatus): string {
  if (status === "settled" || status === "approved" || status === "pre_auth_approved") return "text-pine";
  if (status === "rejected" || status === "pre_auth_rejected") return "text-clay";
  if (status === "queried") return "text-clay";
  return "text-ink-muted";
}

export const canWorkClaims = (role?: string) =>
  ["admin", "manager", "doctor", "supervisor", "reception"].includes(role ?? "");
export const canRecordSettlements = (role?: string) => ["admin", "manager"].includes(role ?? "");
