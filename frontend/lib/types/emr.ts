/** Reception, billing and finance contracts.
 *
 *  Amounts are integer paise everywhere, matching the backend exactly. A
 *  rupee float would reintroduce the precision problem the billing layer
 *  exists to avoid, so conversion happens only for display.
 */
import type { Department, Gender } from "@/lib/types/core";

export type VisitType = "new" | "follow_up" | "review" | "procedure";
export type VisitStatus = "registered" | "in_consultation" | "completed" | "cancelled";
export type PayerType =
  | "self_pay" | "insurance" | "tpa" | "corporate" | "government_scheme";
export type PaymentMode =
  | "cash" | "card" | "upi" | "net_banking" | "cheque"
  | "insurance" | "waiver"
  // Credit the patient already deposited. A payment against the bill, but
  // never a collection — the money arrived on the day it was deposited.
  | "wallet";
export type InvoiceStatus =
  | "draft" | "issued" | "paid" | "partially_paid" | "cancelled" | "refunded";
export type ServiceCategory =
  | "consultation" | "procedure" | "investigation" | "registration" | "other";

export interface PatientCard {
  id: string;
  uhid?: string | null;
  /** The practice the patient is registered with (its three letters). */
  practice?: string | null;
  name: string;
  age: number;
  gender: Gender;
  phone_number: string;
  city?: string | null;
  blood_group?: string | null;
  created_at: string;
}

export interface Visit {
  id: string;
  visit_number: string;
  patient_id: string;
  patient_name: string;
  consultation_id?: string | null;
  department: Department;
  doctor_name: string;
  visit_type: VisitType;
  status: VisitStatus;
  payer_type: PayerType;
  visit_date: string;
  token_number?: number | null;
  registered_by_name: string;
  created_at: string;
}

export interface ServiceItem {
  id: string;
  code: string;
  name: string;
  category: ServiceCategory;
  department?: Department | null;
  rate_paise: number;
  tax_percent: number;
  is_active: boolean;
}

export interface InvoiceLine {
  id: string;
  position: number;
  code?: string | null;
  description: string;
  /** The counter's note against this charge alone. */
  remark?: string | null;
  quantity: number;
  unit_rate_paise: number;
  discount_paise: number;
  tax_percent: number;
  taxable_paise: number;
  tax_paise: number;
  total_paise: number;
}

export interface PaymentRecord {
  id: string;
  receipt_number: string;
  amount_paise: number;
  mode: PaymentMode;
  reference?: string | null;
  received_at: string;
  received_by_name: string;
  is_refund: boolean;
  refund_reason?: string | null;
  /** A struck receipt: the entry was a mistake and no money moved. Distinct
   *  from a refund, where money genuinely went back to the patient. */
  cancelled_at?: string | null;
  cancellation_reason?: string | null;
}

export interface Invoice {
  id: string;
  invoice_number: string;
  visit_id?: string | null;
  patient_id: string;
  status: InvoiceStatus;
  payer_type: PayerType;
  gross_paise: number;
  discount_paise: number;
  taxable_paise: number;
  cgst_paise: number;
  sgst_paise: number;
  igst_paise: number;
  total_paise: number;
  paid_paise: number;
  discount_reason?: string | null;
  issued_at?: string | null;
  cancelled_at?: string | null;
  cancellation_reason?: string | null;
  /** The correction trail: a bill amended before payment, or cancelled and
   *  reinstated, is a fact somebody may have to explain later. */
  amended_at?: string | null;
  amendment_reason?: string | null;
  amendment_count: number;
  /** Set once a consultant payout counted this bill; nothing may change. */
  payout_locked_at?: string | null;
  created_by_name: string;
  created_at: string;
  lines: InvoiceLine[];
  payments: PaymentRecord[];
}

export interface RegisterAndBillResult {
  patient: PatientCard;
  visit: Visit;
  invoice: Invoice;
  payment?: PaymentRecord | null;
}

/** A patient reception has registered who has not yet started voice intake.
 *  This is the handover record between the two terminals. */
export interface QueuedPatient {
  visit_id: string;
  visit_number: string;
  token_number: number | null;
  department: Department;
  doctor_name: string;
  visit_type: VisitType;
  registered_at: string;
  patient: {
    id: string;
    uhid: string | null;
    name: string;
    age: number;
    gender: string;
    phone_number: string;
  };
}


export interface CashSession {
  id: string;
  counter_name: string;
  cashier_name: string;
  status: "open" | "closed" | "reconciled";
  opened_at: string;
  closed_at?: string | null;
  opening_float_paise: number;
  counted_cash_paise?: number | null;
  variance_paise?: number | null;
}

export const PAYMENT_MODES: { value: PaymentMode; label: string }[] = [
  { value: "cash", label: "Cash" },
  { value: "upi", label: "UPI" },
  { value: "card", label: "Card" },
  { value: "net_banking", label: "Net banking" },
  { value: "cheque", label: "Cheque" },
  { value: "insurance", label: "Insurance / TPA" },
  { value: "waiver", label: "Waived" },
];

export const VISIT_TYPES: { value: VisitType; label: string }[] = [
  { value: "new", label: "New patient" },
  { value: "follow_up", label: "Follow-up" },
  { value: "review", label: "Review" },
  { value: "procedure", label: "Procedure only" },
];

/** ₹1,23,456.78 — Indian grouping, from integer paise. */
export function formatINR(paise: number): string {
  const negative = paise < 0;
  const whole = Math.floor(Math.abs(paise) / 100);
  const fraction = Math.abs(paise) % 100;
  const digits = String(whole);

  let grouped: string;
  if (digits.length <= 3) {
    grouped = digits;
  } else {
    const lastThree = digits.slice(-3);
    let rest = digits.slice(0, -3);
    const parts: string[] = [];
    while (rest.length > 2) {
      parts.unshift(rest.slice(-2));
      rest = rest.slice(0, -2);
    }
    if (rest) parts.unshift(rest);
    grouped = [...parts, lastThree].join(",");
  }
  return `${negative ? "-" : ""}₹${grouped}.${String(fraction).padStart(2, "0")}`;
}

/** Rupees typed at the counter into exact paise. */
export function rupeesToPaise(input: string | number): number {
  const value = typeof input === "number" ? input : parseFloat(input || "0");
  if (Number.isNaN(value)) return 0;
  return Math.round(value * 100);
}

/** Paise as a plain rupee figure for a text box: 75000 -> "750", 75050 -> "750.50". */
export function paiseToRupees(paise: number): string {
  if (!paise) return "0";
  return paise % 100 === 0 ? String(paise / 100) : (paise / 100).toFixed(2);
}


// ------------------------------------------------------------ the wallet
export type WalletEntryKind =
  | "deposit"
  | "refund_credit"
  | "applied"
  | "withdrawal"
  | "adjustment";

export const WALLET_KIND_LABEL: Record<WalletEntryKind, string> = {
  deposit: "Advance received",
  refund_credit: "Refund credited",
  applied: "Applied to a bill",
  withdrawal: "Returned to patient",
  adjustment: "Adjustment",
};

export interface WalletEntry {
  id: string;
  kind: WalletEntryKind;
  /** Signed: positive puts money on account, negative takes it off. */
  amount_paise: number;
  balance_after_paise: number;
  invoice_id?: string | null;
  receipt_number?: string | null;
  reason?: string | null;
  created_by_name: string;
  created_at: string;
}

export interface Wallet {
  patient_id: string;
  balance_paise: number;
  entries: WalletEntry[];
}

/** What one payment mode needs recorded, as the server defines it. */
export interface PaymentModeField {
  name: string;
  label: string;
  required: boolean;
  digits?: number | null;
}

export interface PaymentModeSpec {
  mode: PaymentMode;
  collects_cash: boolean;
  fields: PaymentModeField[];
}


// -------------------------------------------------------- bill corrections
export interface InvoiceSummary {
  id: string;
  invoice_number: string;
  status: InvoiceStatus;
  patient_id: string;
  patient_name: string;
  uhid?: string | null;
  visit_number?: string | null;
  visit_id?: string | null;
  total_paise: number;
  paid_paise: number;
  balance_paise: number;
  amendment_count: number;
  /** Counted into a settled consultant payout: nothing about it may change. */
  payout_locked: boolean;
  issued_at?: string | null;
  created_at: string;
}

export interface InvoiceList {
  total: number;
  items: InvoiceSummary[];
}


// ------------------------------------------------------------- the diary
export interface DiaryEntry {
  kind: "opd" | "ipd" | "wallet";
  reference: string;
  date: string;
  description: string;
  gross_paise: number;
  discount_paise: number;
  net_paise: number;
  received_paise: number;
  refunded_paise: number;
  /** What this entry alone still owes. */
  balance_paise: number;
  running_balance_paise: number;
  status: string;
  cancelled: boolean;
  /** Carried onto an inpatient bill — not collectable at the counter. */
  credited_to_ipd: boolean;
  invoice_id?: string | null;
  visit_id?: string | null;
  admission_id?: string | null;
  notes: string[];
}

export interface PatientDiary {
  patient: {
    id: string;
    uhid?: string | null;
    name: string;
    age: number;
    gender: string;
    phone_number: string;
  };
  totals: {
    gross_paise: number;
    discount_paise: number;
    net_paise: number;
    received_paise: number;
    refunded_paise: number;
    outstanding_paise: number;
    wallet_balance_paise: number;
    visit_count: number;
    admission_count: number;
  };
  entries: DiaryEntry[];
}

// ----------------------------------------------------------- price quote
export interface QuoteLine {
  description: string;
  code?: string | null;
  remark?: string | null;
  quantity: number;
  unit_rate_paise: number;
  discount_paise: number;
  total_paise: number;
}

export interface Quote {
  gross_paise: number;
  discount_paise: number;
  taxable_paise: number;
  tax_paise: number;
  total_paise: number;
  /** Why a line came out as it did: a free follow-up, an agreed rate. */
  notes: string[];
  lines: QuoteLine[];
}

/** A rate this organisation has agreed for one service, overriding the price list. */
export interface NegotiatedRate {
  id: string;
  service_item_id: string;
  rate_paise: number;
  notes?: string | null;
}

export interface Organisation {
  id: string;
  code: string;
  name: string;
  payer_type: PayerType;
  contact_person?: string | null;
  phone_number?: string | null;
  email?: string | null;
  default_discount_percent: number;
  credit_days: number;
  is_active: boolean;
}


// ---------------------------------------------------------------- reports
export type ReportColumnType =
  | "text" | "money" | "number" | "date" | "datetime" | "status";

export interface ReportColumn {
  key: string;
  label: string;
  type: ReportColumnType;
  /** Summed into the footer. */
  total: boolean;
  visible: boolean;
  position: number;
}

export interface ReportDefinition {
  key: string;
  title: string;
  description: string;
  single_day: boolean;
  /** A cashier may run this against their own till without finance rights. */
  self_service: boolean;
}

export interface ReportResult {
  key: string;
  title: string;
  description: string;
  date_from: string;
  date_to: string;
  /** Set when the report was narrowed to one person's till. */
  scoped_to?: string | null;
  columns: ReportColumn[];
  rows: Record<string, unknown>[];
  totals: Record<string, number>;
  row_count: number;
}


// ------------------------------------------------- scan-to-upload from a phone
export interface UploadLink {
  consultation_id: string;
  /** What the QR encodes; shown as text too, for a camera that will not focus. */
  url: string;
  token: string;
  expires_in_minutes: number;
  expires_at: string;
  /** A data URI, so the code renders with no library and no second request. */
  qr_data_uri: string;
  /** The configured public address is one a phone cannot reach. */
  unreachable_warning: boolean;
}
