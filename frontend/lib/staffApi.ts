"use client";

/** Typed client for the authenticated staff/clinical endpoints. */
import { API_URL, WS_URL } from "@/lib/api";
import { getToken, clearToken } from "@/lib/auth";
import type {
  Census,
  DeterioratingPatient,
  RunningBill,
  WardBoard,
} from "@/lib/ipdTypes";
import type {
  CashSession,
  QueuedPatient,
  CollectionSummary,
  Invoice,
  PatientCard,
  PaymentRecord,
  RegisterAndBillResult,
  ServiceItem,
  Visit,
} from "@/lib/emrTypes";
import type {
  Delivery,
  DictatedMedicine,
  FormularyMedicine,
  Prescription,
  SafetyAlert,
  SafetyCheckResponse,
} from "@/lib/prescriptionTypes";
import type {
  Catalog,
  InvestigationOrder,
  InvestigationPriority,
  InvestigationReport,
  InvestigationTemplate,
  ReportListItem,
  ReportVersionHistory,
  Workspace,
} from "@/lib/investigationTypes";
import type {
  ConsultationDetail,
  ConsultationListItem,
  ConsultationStats,
  ConsultationStatus,
  CopilotBriefing,
  CopilotDecision,
  Department,
  Paginated,
  PatientHistory,
  PatientListItem,
} from "@/lib/types";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const response = await fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
    cache: "no-store",
  });

  if (response.status === 401) {
    clearToken();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    }
    throw new ApiError(401, "Your session has expired. Please sign in again.");
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep default */
    }
    throw new ApiError(response.status, detail);
  }
  return response.json();
}

function query(params: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const serialized = search.toString();
  return serialized ? `?${serialized}` : "";
}

export interface ConsultationFilters {
  department?: Department;
  status?: ConsultationStatus;
  q?: string;
  patient_id?: string;
  reviewed?: boolean;
  offset?: number;
  limit?: number;
}

export const staffApi = {
  stats: (department?: Department) =>
    request<ConsultationStats>(`/consultations/stats${query({ department })}`),

  consultations: (filters: ConsultationFilters = {}) =>
    request<Paginated<ConsultationListItem>>(`/consultations${query({ ...filters })}`),

  consultation: (id: string) => request<ConsultationDetail>(`/consultations/${id}`),

  copilot: (id: string, refresh = false) =>
    request<CopilotBriefing>(`/consultations/${id}/copilot${query({ refresh })}`),

  recordCopilotDecision: (
    id: string,
    payload: { item_key: string; decision: "accepted" | "dismissed" | "pending"; note?: string }
  ) =>
    request<CopilotDecision & { item_key: string }>(`/consultations/${id}/copilot/decisions`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  markReviewed: (id: string) =>
    request<ConsultationDetail>(`/consultations/${id}/review`, { method: "POST" }),

  patients: (params: { q?: string; offset?: number; limit?: number } = {}) =>
    request<Paginated<PatientListItem>>(`/patients${query({ ...params })}`),

  patientHistory: (id: string) => request<PatientHistory>(`/patients/${id}`),

  // ---------------------------------------------------------- investigations
  catalog: (params: { q?: string; category?: string; department?: string } = {}) =>
    request<Catalog>(`/investigations/catalog${query({ ...params })}`),

  investigationWorkspace: () => request<Workspace>("/investigations/workspace"),

  toggleFavorite: (code: string, favorite: boolean) =>
    request<string[]>("/investigations/favorites", {
      method: "POST",
      body: JSON.stringify({ code, favorite }),
    }),

  createTemplate: (payload: {
    name: string;
    codes: string[];
    description?: string;
    shared?: boolean;
  }) =>
    request<InvestigationTemplate>("/investigations/templates", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteTemplate: async (id: string) => {
    const token = getToken();
    const response = await fetch(`${API_URL}/api/v1/investigations/templates/${id}`, {
      method: "DELETE",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!response.ok && response.status !== 204) {
      throw new ApiError(response.status, "Could not delete the template.");
    }
  },

  createOrder: (payload: {
    patient_id: string;
    consultation_id?: string | null;
    codes: string[];
    priority: InvestigationPriority;
    clinical_notes?: string;
    provisional_diagnosis?: string;
    item_instructions?: Record<string, string>;
  }) =>
    request<InvestigationOrder>("/investigations/orders", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  orders: (params: { patient_id?: string; consultation_id?: string }) =>
    request<Paginated<InvestigationOrder>>(`/investigations/orders${query({ ...params })}`),

  cancelOrder: (id: string) =>
    request<InvestigationOrder>(`/investigations/orders/${id}/cancel`, { method: "POST" }),

  reports: (params: {
    patient_id?: string;
    consultation_id?: string;
    include_superseded?: boolean;
  }) => request<Paginated<ReportListItem>>(`/investigations/reports${query({ ...params })}`),

  report: (id: string) => request<InvestigationReport>(`/investigations/reports/${id}`),

  reportVersions: (id: string) =>
    request<ReportVersionHistory>(`/investigations/reports/${id}/versions`),

  reportFileUrl: (id: string) => `${API_URL}/api/v1/investigations/reports/${id}/file`,

  reprocessReport: (id: string) =>
    request<InvestigationReport>(`/investigations/reports/${id}/reprocess`, { method: "POST" }),

  // ------------------------------------------------------------ prescriptions
  formulary: (params: { q?: string; department?: string; limit?: number } = {}) =>
    request<{ items: FormularyMedicine[]; total: number }>(
      `/prescriptions/formulary${query({ ...params })}`
    ),

  prescriptionCapabilities: () =>
    request<{ pdf: boolean; qr: boolean; messaging_provider: string }>(
      "/prescriptions/capabilities"
    ),

  parseDictation: (transcript: string, patientId?: string) =>
    request<{ medicines: DictatedMedicine[]; alerts: SafetyAlert[]; transcript: string }>(
      "/prescriptions/dictation",
      { method: "POST", body: JSON.stringify({ transcript, patient_id: patientId }) }
    ),

  safetyCheck: (patientId: string, medicines: Record<string, unknown>[]) =>
    request<SafetyCheckResponse>("/prescriptions/safety-check", {
      method: "POST",
      body: JSON.stringify({ patient_id: patientId, medicines }),
    }),

  createPrescription: (payload: Record<string, unknown>) =>
    request<Prescription>("/prescriptions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  prescriptions: (params: { patient_id?: string; consultation_id?: string }) =>
    request<{ items: Prescription[]; total: number }>(`/prescriptions${query({ ...params })}`),

  prescription: (id: string) => request<Prescription>(`/prescriptions/${id}`),

  prescriptionPdfUrl: (id: string) => `${API_URL}/api/v1/prescriptions/${id}/pdf`,

  prescriptionPrefill: (consultationId: string) =>
    request<Record<string, unknown>>(
      `/prescriptions/prefill${query({ consultation_id: consultationId })}`
    ),

  regeneratePrescriptionPdf: (id: string) =>
    request<Prescription>(`/prescriptions/${id}/pdf`, { method: "POST" }),

  sendPrescriptionWhatsApp: (id: string, phoneNumber?: string) =>
    request<Delivery>(`/prescriptions/${id}/send/whatsapp`, {
      method: "POST",
      body: JSON.stringify({ phone_number: phoneNumber ?? null }),
    }),

  prescriptionDeliveries: (id: string) =>
    request<Delivery[]>(`/prescriptions/${id}/deliveries`),

  retryDelivery: (deliveryId: string) =>
    request<Delivery>(`/prescriptions/deliveries/${deliveryId}/retry`, { method: "POST" }),

  // ------------------------------------------------------- reception / EMR
  searchCounterPatients: (q: string) =>
    request<PatientCard[]>(`/reception/patients/search${query({ q })}`),

  registerAndBill: (payload: Record<string, unknown>) =>
    request<RegisterAndBillResult>("/reception/register-and-bill", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  todaysVisits: (params: { department?: string } = {}) =>
    request<Visit[]>(`/reception/visits/today${query({ ...params })}`),

  attachConsultationToVisit: (visitId: string, consultationId: string) =>
    request<Visit>(`/reception/visits/${visitId}/consultation/${consultationId}`, {
      method: "POST",
    }),

  invoice: (id: string) => request<Invoice>(`/reception/invoices/${id}`),

  recordPayment: (invoiceId: string, payload: Record<string, unknown>) =>
    request<PaymentRecord>(`/reception/invoices/${invoiceId}/payments`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  refundInvoice: (invoiceId: string, payload: Record<string, unknown>) =>
    request<PaymentRecord>(`/reception/invoices/${invoiceId}/refund`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // ------------------------------------------------------------- finance
  serviceItems: () => request<ServiceItem[]>("/finance/services"),

  collections: (on?: string) =>
    request<CollectionSummary>(`/finance/collections${query({ on })}`),

  outstandingInvoices: () =>
    request<{ count: number; total_outstanding_paise: number; invoices: Record<string, unknown>[] }>(
      "/finance/outstanding"
    ),

  currentCashSession: () =>
    request<{ open: boolean; session: CashSession | null }>("/finance/cash-sessions/current"),

  openCashSession: (payload: Record<string, unknown>) =>
    request<CashSession>("/finance/cash-sessions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  closeCashSession: (id: string, payload: Record<string, unknown>) =>
    request<{ session: CashSession; totals_by_mode: Record<string, number> }>(
      `/finance/cash-sessions/${id}/close`,
      { method: "POST", body: JSON.stringify(payload) }
    ),

  // ------------------------------------------------------------------ IPD
  wardBoard: (params: { department?: string } = {}) =>
    request<{ wards: WardBoard[] }>(`/ipd/board${query({ ...params })}`),

  ipdCensus: () => request<Census>("/ipd/census"),

  deterioratingPatients: (threshold = 5) =>
    request<{ threshold: number; count: number; patients: DeterioratingPatient[] }>(
      `/ipd/alerts/deteriorating${query({ threshold })}`
    ),

  admissionChart: (id: string) =>
    request<Record<string, unknown>>(`/ipd/admissions/${id}`),

  admitPatient: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/ipd/admissions", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  recordVitals: (admissionId: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/ipd/admissions/${admissionId}/vitals`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  transferBed: (admissionId: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/ipd/admissions/${admissionId}/transfer`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  runningBill: (admissionId: string) =>
    request<RunningBill>(`/ipd/admissions/${admissionId}/bill`),

  draftDischargeSummary: (admissionId: string) =>
    request<{ note_id: string; content: string; requires_review: boolean; notice: string }>(
      `/ipd/admissions/${admissionId}/ai/discharge-summary`,
      { method: "POST" }
    ),

  reviewNote: (noteId: string, content: string) =>
    request<Record<string, unknown>>(`/ipd/notes/${noteId}/review`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),

  dischargePatient: (admissionId: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/ipd/admissions/${admissionId}/discharge`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // ---------------------------------------- reception -> voice intake
  intakeQueue: (params: { department?: string } = {}) =>
    request<{ count: number; patients: QueuedPatient[] }>(
      `/reception/intake-queue${query({ ...params })}`
    ),

  startConsultationFromVisit: (visitId: string) =>
    request<{
      consultation_id: string;
      patient_id: string;
      department: string;
      session_token: string;
      ws_path: string;
    }>("/consultations/start-from-visit", {
      method: "POST",
      body: JSON.stringify({ visit_id: visitId }),
    }),

  dictationWsUrl: () => `${WS_URL}/api/v1/ws/dictation?token=${encodeURIComponent(getToken() ?? "")}`,

  /** Multipart upload — Content-Type must be left to the browser for the boundary. */
  uploadReport: async (form: FormData): Promise<InvestigationReport> => {
    const token = getToken();
    const response = await fetch(`${API_URL}/api/v1/investigations/reports`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (response.status === 401) {
      clearToken();
      throw new ApiError(401, "Your session has expired. Please sign in again.");
    }
    if (!response.ok) {
      let detail = `Upload failed (${response.status})`;
      try {
        const body = await response.json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        /* keep default */
      }
      throw new ApiError(response.status, detail);
    }
    return response.json();
  },
};
