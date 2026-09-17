/** Contracts for the Visit Pad (mirrors backend/app/schemas/pad_schemas.py). */
import type { Department } from "@/lib/types/core";

export type SectionKind = "text" | "fields" | "list" | "ai";
export type FieldType =
  | "text"
  | "textarea"
  | "number"
  | "date"
  | "select"
  | "multiselect"
  | "checkbox";
export type AISource =
  | "intake_summary"
  | "red_flags"
  | "differentials"
  | "suggested_investigations";

export interface FieldSpec {
  key: string;
  label: string;
  type: FieldType;
  unit?: string | null;
  options: string[];
  required: boolean;
  catalogue_category?: string | null;
}

export interface SectionSpec {
  key: string;
  title: string;
  kind: SectionKind;
  visible_in_pad: boolean;
  visible_in_print: boolean;
  carry_forward: boolean;
  catalogue_category?: string | null;
  placeholder?: string | null;
  fields: FieldSpec[];
  ai_source?: AISource | null;
}

export type FieldValue = string | number | boolean | string[] | null;

/** One section's content. Which keys are present depends on the kind. */
export interface SectionValue {
  text?: string;
  items?: string[];
  fields?: Record<string, FieldValue>;
}

export interface SectionOrigin {
  source: string;
  drafted_at?: string;
  edited?: boolean;
  edited_by?: string;
  template_id?: string;
  name?: string;
  document_id?: string;
  signed_at?: string | null;
}

export type PadStatus = "draft" | "signed" | "superseded";

export type DocumentFamily = "certificate" | "consent";

export interface PadDocumentTypeInfo {
  key: string;
  label: string;
  scope: string;
  authority: "doctor" | "nursing";
  family?: DocumentFamily | null;
  /** A link the document cannot be written without, e.g. "admission". */
  requires?: string | null;
}

/** The fixed wording a consent form prints. */
export interface FormWording {
  key: string;
  label: string;
  label_hi?: string | null;
  family: DocumentFamily;
  requires?: string | null;
  statement?: { en: string[]; hi: string[] } | null;
}

export interface PadDocument {
  id: string;
  document_type: string;
  title: string;
  patient_id: string;
  consultation_id?: string | null;
  admission_id?: string | null;
  surgery_id?: string | null;
  department?: Department | null;
  layout_revision: number;
  sections: SectionSpec[];
  values: Record<string, SectionValue>;
  provenance: Record<string, SectionOrigin>;
  status: PadStatus;
  author_name: string;
  signed_by_name?: string | null;
  signed_at?: string | null;
  group_id: string;
  version: number;
  supersedes_id?: string | null;
  amendment_reason?: string | null;
  print_count: number;
  /** Certificates and consent forms: given at first signing, kept by corrections. */
  serial_number?: string | null;
  paper_signed_at?: string | null;
  paper_signed_by_name?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PadDocumentSummary {
  id: string;
  document_type: string;
  title: string;
  consultation_id?: string | null;
  admission_id?: string | null;
  surgery_id?: string | null;
  serial_number?: string | null;
  paper_signed_at?: string | null;
  status: PadStatus;
  version: number;
  author_name: string;
  signed_by_name?: string | null;
  signed_at?: string | null;
  created_at: string;
}

export interface PadTemplate {
  id: string;
  document_type: string;
  name: string;
  description?: string | null;
  owner_name: string;
  shared: boolean;
  use_count: number;
  section_keys: string[];
}

export type LayoutScope = "personal" | "department" | "hospital";

export interface PadLayout {
  document_type: string;
  document_label: string;
  scope: LayoutScope | "default";
  name: string;
  sections: SectionSpec[];
  revision: number;
  updated_by_name?: string | null;
  variables: Record<string, string>;
  /** Section key -> field keys the system needs; they cannot be removed. */
  protected?: Record<string, string[]>;
  /** Fixed layout: certificates, consents, radiology. */
  locked?: boolean;
}

export interface CatalogueSuggestion {
  text: string;
  use_count: number;
}

export interface ArrangementItem {
  key: string;
  visible_in_pad: boolean;
  visible_in_print: boolean;
}
