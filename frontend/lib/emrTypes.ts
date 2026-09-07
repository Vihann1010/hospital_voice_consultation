/** Reception, billing and finance contracts.
 *
 *  Amounts are integer paise everywhere, matching the backend exactly. A
 *  rupee float would reintroduce the precision problem the billing layer
 *  exists to avoid, so conversion happens only for display.
 */
import type { Department, Gender } from "@/lib/types";

export type VisitType = "new" | "follow_up" | "review" | "procedure";
export type VisitStatus = "registered" | "in_consultation" | "completed" | "cancelled";
export type PayerType =
  | "self_pay" | "insurance" | "tpa" | "corporate" | "government_scheme";
export type PaymentMode =
  | "cash" | "card" | "upi" | "net_banking" | "insurance" | "waiver";
export type InvoiceStatus =
  | "draft" | "issued" | "paid" | "partially_paid" | "cancelled" | "refunded";
export type ServiceCategory =
  | "consultation" | "procedure" | "investigation" | "registration" | "other";

export interface PatientCard {
  id: string;
  uhid?: string | null;
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
  issued_at?: string | null;
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

export interface CollectionSummary {
  on: string;
  invoice_count: number;
  patient_count: number;
  billed_paise: number;
  discount_paise: number;
  collected_paise: number;
  refunded_paise: number;
  outstanding_paise: number;
  by_mode: Record<string, number>;
  by_department: Record<string, number>;
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
