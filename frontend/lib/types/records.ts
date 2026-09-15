/** Patient file attachments, the radiology worklist and the medical records bundle. */

export type PatientFileCategory =
  | "identity_proof"
  | "referral_letter"
  | "previous_records"
  | "outside_investigation"
  | "signed_consent"
  | "clinical_photograph"
  | "insurance"
  | "other";

export interface FileCategoryOption {
  key: PatientFileCategory;
  label: string;
}

export interface PatientFileRecord {
  id: string;
  patient_id: string;
  consultation_id?: string | null;
  admission_id?: string | null;
  pad_document_id?: string | null;
  category: PatientFileCategory;
  title: string;
  document_date?: string | null;
  notes?: string | null;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  uploaded_by_name: string;
  withdrawn_at?: string | null;
  withdrawn_by_name?: string | null;
  withdraw_reason?: string | null;
  created_at: string;
}

export interface RadiologyWorkItem {
  item_id: string;
  code: string;
  name: string;
  category: string;
  site?: string | null;
  order_id: string;
  consultation_id?: string | null;
  ordered_at: string;
  ordered_by_name: string;
  priority: "routine" | "urgent" | "stat";
  clinical_notes?: string | null;
  provisional_diagnosis?: string | null;
  reported: boolean;
  patient: { id: string; name: string; uhid: string | null; age: number; gender: string };
  report: { id: string; status: "draft" | "signed"; serial_number: string | null; author_name: string } | null;
}

export interface ChecklistItem {
  key: string;
  section: string;
  title: string;
  kind: string;
  on: string | null;
  status: string;
  included: boolean;
  note: string | null;
}

export interface RecordsChecklist {
  admission: {
    id: string;
    ip_number: string;
    status: string;
    admitted_on: string | null;
    discharged_on: string | null;
    patient_name: string;
    uhid: string | null;
  };
  items: ChecklistItem[];
  missing: string[];
}

export interface BundleJob {
  job_id: string;
  admission_id: string;
  status: "running" | "done" | "failed";
  total: number;
  done: number;
  current: string;
  error: string | null;
  pages: number;
  skipped: { title: string; reason: string }[];
  ready: boolean;
}

export function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function openBlob(blob: Blob) {
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
