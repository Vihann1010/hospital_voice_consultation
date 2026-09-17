/** The books and consultant payouts — mirrors app/api/v1/routes/accounts.py. Money is integer paise. */

export type VoucherType = "sales" | "receipt" | "payment" | "journal" | "contra";

export interface AccountGroup {
  id: string;
  code: string;
  name: string;
  nature: string;
  parent_id: string | null;
  is_system: boolean;
}

export interface LedgerRow {
  id: string;
  code: string;
  name: string;
  group_id: string;
  group_name: string;
  group_path: string;
  nature: string;
  system_key: string | null;
  consultant_id: string | null;
  /** Signed: debit positive, credit negative. */
  opening_balance_paise: number;
  balance_paise: number;
  is_active: boolean;
  is_system: boolean;
  notes: string | null;
}

export interface StatementRow {
  voucher_id: string;
  voucher_number: string;
  voucher_type: VoucherType;
  voucher_date: string;
  narration: string;
  status: string;
  debit_paise: number;
  credit_paise: number;
  balance_paise: number;
}

export interface LedgerStatement {
  ledger: LedgerRow;
  date_from: string;
  date_to: string;
  opening_paise: number;
  rows: StatementRow[];
  closing_paise: number;
  total_debit_paise: number;
  total_credit_paise: number;
}

export interface TrialBalanceRow {
  ledger_id: string;
  code: string;
  name: string;
  group_name: string;
  group_path: string;
  nature: string;
  opening_paise: number;
  debit_paise: number;
  credit_paise: number;
  closing_paise: number;
}

export interface TrialBalance {
  date_from: string;
  date_to: string;
  rows: TrialBalanceRow[];
  totals: { opening_paise: number; debit_paise: number; credit_paise: number; closing_paise: number };
  balanced: boolean;
  opening_difference_paise: number;
}

export interface VoucherRow {
  id: string;
  voucher_number: string;
  voucher_type: VoucherType;
  financial_year: string;
  voucher_date: string;
  narration: string;
  source_type: string | null;
  source_id: string | null;
  status: "posted" | "reversed";
  reversal_of_id: string | null;
  is_manual: boolean;
  created_by_name: string;
  reversed_at: string | null;
  reversed_by_name: string | null;
  reversal_reason: string | null;
  total_paise: number;
}

export interface VoucherDetail extends VoucherRow {
  lines: { ledger_id: string; ledger_name: string; ledger_code: string; debit_paise: number; credit_paise: number; narration: string | null }[];
}

export interface PostingRun {
  id: string;
  status: "running" | "done" | "partial" | "skipped" | "failed";
  started_at: string;
  finished_at: string | null;
  triggered_by: string;
  summary: {
    posted?: number;
    replaced?: number;
    reversed?: number;
    unchanged?: number;
    nothing?: number;
    failed?: number;
    full?: boolean;
    exceptions?: { source: string; error: string }[];
  };
  error: string | null;
}

export interface PayoutConsultant {
  id: string;
  full_name: string;
  department: string;
  payout_share_percent: number;
  payout_categories: string[];
  is_active: boolean;
}

export interface PayoutOptions {
  categories: string[];
  pay_modes: string[];
  consultants: PayoutConsultant[];
}

export interface PayoutItem {
  kind: "bill" | "refund";
  invoice_id: string | null;
  payment_id: string | null;
  invoice_number: string;
  invoice_date: string;
  patient_name: string;
  eligible_paise: number;
  base_paise: number;
  share_paise: number;
}

export interface PayoutPreview {
  consultant: { id: string; full_name: string; department: string };
  share_percent: number;
  categories: string[];
  date_from: string;
  date_to: string;
  items: PayoutItem[];
  waiting: {
    invoice_number: string;
    invoice_date: string;
    patient_name: string;
    total_paise: number;
    paid_paise: number;
    eligible_paise: number;
    reason: string;
  }[];
  base_paise: number;
  share_paise: number;
}

export interface Payout {
  id: string;
  payout_number: string;
  consultant_id: string;
  consultant_name: string;
  period_from: string;
  period_to: string;
  share_percent: number;
  categories: string[];
  base_paise: number;
  share_paise: number;
  tds_paise: number;
  net_paid_paise: number;
  status: "approved" | "paid" | "cancelled";
  approved_at: string;
  approved_by_name: string;
  paid_at: string | null;
  paid_on: string | null;
  paid_by_name: string | null;
  payment_mode: string | null;
  payment_reference: string | null;
  cancelled_at: string | null;
  cancelled_by_name: string | null;
  cancel_reason: string | null;
  notes: string | null;
  items?: PayoutItem[];
}

export const VOUCHER_TYPE_LABEL: Record<string, string> = {
  sales: "Sales",
  receipt: "Receipt",
  payment: "Payment",
  journal: "Journal",
  contra: "Contra",
};

export const CATEGORY_LABEL: Record<string, string> = {
  consultation: "Consultations",
  procedure: "Procedures",
  investigation: "Investigations",
  registration: "Registration",
  other: "Other services",
};

export const PAY_MODE_LABEL: Record<string, string> = {
  cash: "Cash",
  upi: "UPI",
  net_banking: "Net banking",
  cheque: "Cheque",
};

/** A signed balance the way an accountant reads it: 1,200.00 Dr. */
export function drCr(paise: number, format: (value: number) => string): string {
  if (paise === 0) return format(0);
  return `${format(Math.abs(paise))} ${paise > 0 ? "Dr" : "Cr"}`;
}

/** 1 April of the financial year a hospital date falls in. */
export function financialYearStart(isoDate: string): string {
  const [year, month] = isoDate.split("-").map(Number);
  return `${month >= 4 ? year : year - 1}-04-01`;
}

export const canManageAccounts = (role?: string) => ["admin", "manager"].includes(role ?? "");
