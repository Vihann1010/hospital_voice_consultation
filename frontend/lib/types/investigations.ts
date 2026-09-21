/** Contracts for the investigation module (mirrors investigation_schemas.py). */
import type { Department } from "@/lib/types/core";

export type InvestigationCategory =
  | "blood" | "urine" | "xray" | "mri" | "ct" | "ultrasound"
  | "dexa" | "orthopedic" | "gynecology" | "gastroenterology" | "endoscopy"
  | "hormonal" | "tumor_markers";

export type InvestigationPriority = "routine" | "urgent" | "stat";
export type OrderStatus = "draft" | "issued" | "partially_reported" | "completed" | "cancelled";
export type ReportStatus = "uploaded" | "extracting" | "analyzed" | "failed" | "superseded";
export type AbnormalFlag =
  | "normal" | "low" | "high" | "critical_low" | "critical_high" | "abnormal" | "unknown";

/** What the patient handed over. Decides which analyser reads it. */
export type DocumentKind = "prescription" | "lab_report" | "imaging" | "other";

/**
 * Whether the contents may be shown as fact.
 *
 * `unclear` is not an error state — the file uploaded and stored perfectly
 * well. It means nothing on it could be read with enough confidence to put in
 * front of a doctor, so the screen says so instead of showing a guess.
 */
export type ReportClarity = "clear" | "unclear" | "not_analysed";

export interface Investigation {
  code: string;
  name: string;
  category: InvestigationCategory;
  category_label: string;
  aliases: string[];
  specimen_or_site?: string | null;
  preparation?: string | null;
  turnaround?: string | null;
  departments: Department[];
  note?: string | null;
}

export interface Panel {
  code: string;
  name: string;
  description: string;
  members: Investigation[];
}

export interface CatalogCategory {
  value: InvestigationCategory;
  label: string;
  count: number;
}

export interface Catalog {
  categories: CatalogCategory[];
  investigations: Investigation[];
  panels: Panel[];
  total: number;
}

export interface InvestigationTemplate {
  id: string;
  name: string;
  description?: string | null;
  department?: Department | null;
  codes: string[];
  shared: boolean;
}

export interface Workspace {
  favorites: string[];
  recent: { code: string; name: string; uses: number }[];
  templates: InvestigationTemplate[];
  capabilities: {
    pdf_text?: boolean;
    ocr_images?: boolean;
    ocr_scanned_pdf?: boolean;
    languages?: string;
  };
}

export interface OrderItem {
  id: string;
  code: string;
  name: string;
  category: InvestigationCategory;
  specimen_or_site?: string | null;
  preparation?: string | null;
  instructions?: string | null;
  position: number;
  reported: boolean;
}

export interface InvestigationOrder {
  id: string;
  patient_id: string;
  consultation_id?: string | null;
  department: Department;
  status: OrderStatus;
  priority: InvestigationPriority;
  clinical_notes?: string | null;
  provisional_diagnosis?: string | null;
  ordered_by_name: string;
  issued_at?: string | null;
  created_at: string;
  items: OrderItem[];
}

export interface ReportResult {
  printed_name: string;
  display_name: string;
  analyte_key?: string | null;
  value?: number | null;
  value_text?: string | null;
  unit?: string | null;
  reference_low?: number | null;
  reference_high?: number | null;
  reference_text?: string | null;
  reference_source: "report" | "builtin" | "none";
  flag: AbnormalFlag;
  deviation_note?: string | null;
  note?: string | null;
  section?: string | null;
}

/** One medicine read off a prescription. */
export interface MedicineRead {
  raw_line: string;
  /** The formulary name. Never the raw OCR token. */
  name: string;
  /** How it was printed, when that differed from the formulary name. */
  read_as?: string | null;
  ingredients: string[];
  strength?: string | null;
  dose_notation?: string | null;
  frequency?: string | null;
  duration?: string | null;
  timing?: string | null;
  /** False for a near match, which must never be shown as a confirmed drug. */
  exact: boolean;
}

export interface PrescriptionReading {
  medicines: MedicineRead[];
  possible_medicines: MedicineRead[];
  unidentified_lines: string[];
  problems: string[];
  needs_manual_check: boolean;
}

export interface ImagingReading {
  modality?: string | null;
  impression: string[];
  findings: string[];
}

export interface ReportAnalysis {
  extraction?: {
    method?: string;
    page_count?: number | null;
    warning?: string | null;
    characters?: number;
    legible?: boolean;
  };
  document_kind?: DocumentKind | null;
  declared_kind?: DocumentKind | null;
  detected_kind?: DocumentKind | null;
  detection_confident?: boolean;
  detection_reasons?: string[];
  clarity?: ReportClarity;
  unclear_reason?: string | null;
  needs_manual_check?: boolean;
  prescription?: PrescriptionReading;
  imaging?: ImagingReading;
  /** Lines carrying numbers that could not be read as a measurement. */
  uninterpreted_lines?: string[];
  results?: ReportResult[];
  abnormal?: ReportResult[];
  critical?: ReportResult[];
  abnormal_count?: number;
  critical_count?: number;
  recognised_rate?: number;
  narrative_lines?: string[];
  summary?: {
    report_type?: string | null;
    headline?: string | null;
    doctor_summary?: string | null;
    key_findings?: {
      finding: string;
      significance?: string | null;
      severity: "incidental" | "notable" | "significant" | "urgent";
    }[];
    patterns_noticed?: string[];
    comparison_with_previous?: string | null;
    suggested_next_steps?: string[];
    limitations?: string | null;
    disclaimer?: string;
  };
  summary_error?: string;
}

export interface InvestigationReport {
  id: string;
  patient_id: string;
  consultation_id?: string | null;
  order_id?: string | null;
  group_id: string;
  version: number;
  replaces_id?: string | null;
  revision_note?: string | null;
  title: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  document_kind?: DocumentKind | null;
  status: ReportStatus;
  extraction_method?: string | null;
  page_count?: number | null;
  analysis?: ReportAnalysis | null;
  error_detail?: string | null;
  uploaded_by_name: string;
  created_at: string;
}

export interface ReportListItem {
  id: string;
  group_id: string;
  version: number;
  title: string;
  original_filename: string;
  content_type: string;
  document_kind?: DocumentKind | null;
  status: ReportStatus;
  abnormal_count: number;
  critical_count: number;
  clarity?: ReportClarity | null;
  needs_manual_check?: boolean;
  headline?: string | null;
  uploaded_by_name: string;
  created_at: string;
}

export interface ReportVersionHistory {
  group_id: string;
  current: InvestigationReport;
  versions: ReportListItem[];
}

export const CATEGORY_ORDER: InvestigationCategory[] = [
  "blood", "urine", "xray", "mri", "ct", "ultrasound", "endoscopy",
  "dexa", "orthopedic", "gynecology", "gastroenterology", "hormonal", "tumor_markers",
];

export const DOCUMENT_KIND_LABEL: Record<DocumentKind, string> = {
  prescription: "Prescription",
  lab_report: "Lab report",
  imaging: "Scan or X-ray",
  other: "Other document",
};

/** The one sentence shown wherever a document could not be read. */
export const UNCLEAR_HEADLINE = "Report unclear — please go through it manually.";

export const FLAG_LABEL: Record<AbnormalFlag, string> = {
  normal: "Normal",
  low: "Low",
  high: "High",
  critical_low: "Critically low",
  critical_high: "Critically high",
  abnormal: "Abnormal",
  unknown: "Not compared",
};
