"use client";

/** Typed client for the authenticated staff/clinical endpoints. */
import { API_URL, WS_URL } from "@/lib/api";
import { getToken, clearToken } from "@/lib/auth";
import type { StaffRole, User } from "@/lib/types";
import type {
  Appointment,
  AppointmentStatus,
  Board,
  Consultant,
  Slot,
} from "@/lib/appointmentTypes";
import type {
  Milestone,
  Operation,
  Surgery,
  TheatreOptions,
  TheatreRoom,
} from "@/lib/theatreTypes";
import type {
  LabMaster,
  LabOptions,
  LabPatient,
  LabRequest,
  LabRequestSummary,
  LabTest,
  PatientLabResult,
  PendingLabOrder,
  PrintoutReading,
} from "@/lib/labTypes";
import type {
  BundleJob,
  FileCategoryOption,
  PatientFileRecord,
  RadiologyWorkItem,
  RecordsChecklist,
} from "@/lib/recordsTypes";
import type {
  AdmissionChart,
  AdmissionLeave,
  Census,
  DeterioratingPatient,
  DrugChart,
  DrugCheck,
  RoomChargeRun,
  RoomChargeRuns,
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
  InvoiceList,
  Organisation,
  PatientDiary,
  PaymentModeSpec,
  Quote,
  ReportColumn,
  ReportDefinition,
  ReportResult,
  UploadLink,
  Wallet,
  WalletEntry,
} from "@/lib/emrTypes";
import type {
  Delivery,
  DictatedMedicine,
  FormularyMedicine,
  MedicineTemplate,
  Prescription,
  PrescriptionAssist,
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
  ArrangementItem,
  CatalogueSuggestion,
  FormWording,
  LayoutScope,
  PadDocument,
  PadDocumentSummary,
  PadDocumentTypeInfo,
  PadLayout,
  PadTemplate,
  SectionSpec,
  SectionValue,
} from "@/lib/padTypes";
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
  const financeUnlock =
    typeof window !== "undefined" ? sessionStorage.getItem("finance_unlock") : null;
  const response = await fetch(`${API_URL}/api/v1${path}`, {
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(financeUnlock && path.startsWith("/finance/")
        ? { "X-Finance-Unlock": financeUnlock }
        : {}),
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
  visit_type?: "new" | "follow_up" | "review" | "procedure";
  offset?: number;
  limit?: number;
}

export const staffApi = {
  stats: (department?: Department) =>
    request<ConsultationStats>(`/consultations/stats${query({ department })}`),

  consultations: (filters: ConsultationFilters = {}) =>
    request<Paginated<ConsultationListItem>>(`/consultations${query({ ...filters })}`),

  consultation: (id: string) => request<ConsultationDetail>(`/consultations/${id}`),

  updateConsultationVitals: (id: string, payload: Record<string, string>) =>
    request<ConsultationDetail>(`/consultations/${id}/vitals`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

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

  medicineTemplates: (params: { q?: string; department?: string; limit?: number } = {}) =>
    request<{ items: MedicineTemplate[]; total: number }>(
      `/prescriptions/templates${query({ ...params })}`
    ),

  prescriptionAssist: (payload: { consultation_id?: string | null; diagnosis: string; department?: string }) =>
    request<PrescriptionAssist>('/prescriptions/assist', {
      method: 'POST', body: JSON.stringify(payload),
    }),

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
  invoicePdfUrl: (id: string) => `${API_URL}/api/v1/reception/invoices/${id}/pdf`,

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

  /** Create the patient record only — no visit, no token, no bill. */
  registerPatient: (payload: Record<string, unknown>) =>
    request<PatientCard>("/reception/patients", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

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

  /** Everything a patient has been charged and has paid, in one list. */
  patientDiary: (patientId: string) =>
    request<PatientDiary>(`/reception/patients/${patientId}/diary`),

  /** Price a bill without raising it, so a free follow-up shows before the
   *  patient is asked for money rather than as a surprise zero afterwards. */
  quoteBill: (payload: Record<string, unknown>) =>
    request<Quote>("/reception/quote", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  organisations: (activeOnly = true) =>
    request<Organisation[]>(`/masters/organisations${query({ active_only: activeOnly })}`),

  invoices: (params: {
    q?: string;
    patient_id?: string;
    status?: string;
    from?: string;
    to?: string;
    limit?: number;
    offset?: number;
  } = {}) => request<InvoiceList>(`/reception/invoices${query({ ...params })}`),

  // ------------------------------------------------------------ corrections
  cancelInvoice: (id: string, reason: string) =>
    request<Invoice>(`/reception/invoices/${id}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  uncancelInvoice: (id: string, reason: string) =>
    request<Invoice>(`/reception/invoices/${id}/uncancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  cancelReceipt: (paymentId: string, reason: string) =>
    request<PaymentRecord>(`/reception/receipts/${paymentId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  cancelVisit: (visitId: string, reason: string) =>
    request<Visit>(`/reception/visits/${visitId}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  uncancelVisit: (visitId: string) =>
    request<Visit>(`/reception/visits/${visitId}/uncancel`, { method: "POST" }),

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

  // ------------------------------------------------------ wallet / receipts
  /** What each payment mode requires. Served so the counter and the
   *  validator cannot disagree about whether a cheque needs a bank name. */
  paymentModes: () =>
    request<{ modes: PaymentModeSpec[] }>("/reception/payment-modes"),

  wallet: (patientId: string, limit = 50) =>
    request<Wallet>(`/reception/patients/${patientId}/wallet${query({ limit })}`),

  walletDeposit: (patientId: string, payload: Record<string, unknown>) =>
    request<WalletEntry>(`/reception/patients/${patientId}/wallet/deposit`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  walletWithdraw: (patientId: string, payload: Record<string, unknown>) =>
    request<WalletEntry>(`/reception/patients/${patientId}/wallet/withdraw`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  payFromWallet: (invoiceId: string, amountPaise: number) =>
    request<PaymentRecord>(`/reception/invoices/${invoiceId}/pay-from-wallet`, {
      method: "POST",
      body: JSON.stringify({ amount_paise: amountPaise }),
    }),

  receiptPdfUrl: (paymentId: string) =>
    `${API_URL}/api/v1/reception/receipts/${paymentId}/pdf`,

  walletReceiptPdfUrl: (entryId: string) =>
    `${API_URL}/api/v1/reception/wallet-entries/${entryId}/pdf`,

  // -------------------------------------------------- appointments / board
  consultants: (params: { active_only?: boolean } = {}) =>
    request<Consultant[]>(`/masters/consultants${query({ ...params })}`),

  appointmentSlots: (consultantId: string, on: string) =>
    request<Slot[]>(`/appointments/slots${query({ consultant_id: consultantId, on })}`),

  nextAppointmentSlot: (consultantId: string) =>
    request<{ consultant_id: string; next_available: string | null }>(
      `/appointments/next-slot${query({ consultant_id: consultantId })}`
    ),

  queueBoard: (params: { on?: string; department?: string; consultant_id?: string } = {}) =>
    request<Board>(`/appointments/board${query({ ...params })}`),

  bookAppointment: (payload: Record<string, unknown>) =>
    request<Appointment>("/appointments", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  rescheduleAppointment: (id: string, scheduledStart: string) =>
    request<Appointment>(`/appointments/${id}/reschedule`, {
      method: "POST",
      body: JSON.stringify({ scheduled_start: scheduledStart }),
    }),

  cancelAppointment: (id: string, reason: string) =>
    request<Appointment>(`/appointments/${id}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  setAppointmentStatus: (id: string, status: AppointmentStatus) =>
    request<Appointment>(`/appointments/${id}/status`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),

  /**
   * Check a booking in. For a phone booking this is also the moment of
   * registration, so it carries either the new patient's details or the id
   * of the record the clerk recognised.
   */
  checkInAppointment: (id: string, payload: Record<string, unknown> = {}) =>
    request<Visit>(`/appointments/${id}/check-in`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  /** Mint a short-lived QR the patient scans to upload reports from a phone. */
  createUploadLink: (consultationId: string) =>
    request<UploadLink>(`/upload-links/${consultationId}`, { method: "POST" }),

  // ------------------------------------------------------------- reports
  /** The front-office reports. Named apart from `reports`, which is the
   *  investigation reports a patient uploaded — a different thing entirely. */
  reportCatalogue: () => request<ReportDefinition[]>("/reports"),

  runReport: (key: string, params: { from?: string; to?: string; mine?: boolean } = {}) =>
    request<ReportResult>(`/reports/${key}${query({ ...params })}`),

  reportCsvUrl: (key: string, params: { from?: string; to?: string; mine?: boolean } = {}) =>
    `${API_URL}/api/v1/reports/${key}/csv${query({ ...params })}`,

  setReportColumns: (key: string, columns: Record<string, unknown>[]) =>
    request<ReportColumn[]>(`/reports/${key}/columns`, {
      method: "PUT",
      body: JSON.stringify(columns),
    }),

  // ------------------------------------------------------------- finance
  verifyFinancePin: (pin: string) =>
    request<{ token: string }>("/finance/verify-pin", {
      method: "POST",
      body: JSON.stringify({ pin }),
    }),

  serviceItems: () => request<ServiceItem[]>("/finance/services"),

  collections: (on?: string) =>
    request<CollectionSummary>(`/finance/collections${query({ on })}`),

  outstandingInvoices: () =>
    request<{ count: number; total_outstanding_paise: number; invoices: Record<string, unknown>[] }>(
      "/finance/outstanding"
    ),

  currentCashSession: () =>
    request<{
      open: boolean;
      session: CashSession | null;
      cash_taken_paise?: number;
      expected_cash_paise?: number;
    }>("/finance/cash-sessions/current"),

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

  searchPatientsForAdmission: (q: string) =>
    request<{ id: string; uhid: string | null; name: string; age: number;
              gender: string; phone_number: string; blood_group?: string | null }[]>(
      `/ipd/patients/search${query({ q })}`
    ),

  registerPatientForAdmission: (payload: Record<string, unknown>) =>
    request<{ id: string; uhid: string; name: string }>("/ipd/patients", {
      method: "POST", body: JSON.stringify(payload),
    }),

  postAdmissionCharge: (admissionId: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/ipd/admissions/${admissionId}/charges`, {
      method: "POST", body: JSON.stringify(payload),
    }),

  raiseIpdInvoice: (
    admissionId: string,
    params: {
      discount_paise?: number;
      discount_reason?: string;
      payer_covered_paise?: number;
    } = {}
  ) =>
    request<{ invoice: Record<string, any>; ip_number: string;
              advance_paid_paise: number; balance_paise: number }>(
      `/ipd/admissions/${admissionId}/invoice${query({ ...params })}`,
      { method: "POST" }
    ),

  admissionChart: (id: string) =>
    request<AdmissionChart>(`/ipd/admissions/${id}`),

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

  // ------------------------------------------------------------ drug chart
  drugChart: (admissionId: string, on?: string) =>
    request<DrugChart>(`/ipd/admissions/${admissionId}/drug-chart${query({ on })}`),
  checkMedication: (admissionId: string, drugName: string) =>
    request<DrugCheck>(`/ipd/admissions/${admissionId}/medications/check`, {
      method: "POST",
      body: JSON.stringify({ drug_name: drugName }),
    }),
  orderMedication: (admissionId: string, payload: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/ipd/admissions/${admissionId}/medications`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  signDose: (
    doseId: string,
    payload: { was_given: boolean; omission_reason?: string; notes?: string }
  ) =>
    request<Record<string, unknown>>(`/ipd/medications/${doseId}/administer`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  giveAsNeeded: (orderId: string, notes?: string) =>
    request<Record<string, unknown>>(`/ipd/medications/${orderId}/give`, {
      method: "POST",
      body: JSON.stringify({ notes: notes || null }),
    }),
  stopMedication: (orderId: string, reason: string) =>
    request<Record<string, unknown>>(`/ipd/medications/${orderId}/stop${query({ reason })}`, {
      method: "POST",
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

  // -------------------------------------------------------------- theatre
  theatreOptions: () => request<TheatreOptions>("/theatre/options"),
  theatreRooms: (includeInactive = false) =>
    request<TheatreRoom[]>(`/theatre/rooms${query({ include_inactive: includeInactive || undefined })}`),
  saveTheatreRoom: (payload: Omit<TheatreRoom, "id">, id?: string) =>
    request<TheatreRoom>(id ? `/theatre/rooms/${id}` : "/theatre/rooms", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    }),
  theatreOperations: (
    params: { q?: string; department?: string; include_inactive?: boolean; limit?: number } = {}
  ) => request<Operation[]>(`/theatre/operations${query({ ...params })}`),
  saveOperation: (payload: Omit<Operation, "id">, id?: string) =>
    request<Operation>(id ? `/theatre/operations/${id}` : "/theatre/operations", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    }),
  surgeries: (params: { on?: string; admission_id?: string; room_id?: string } = {}) =>
    request<Surgery[]>(`/theatre/surgeries${query({ ...params })}`),
  surgery: (id: string) => request<Surgery>(`/theatre/surgeries/${id}`),
  bookSurgery: (payload: Record<string, unknown>) =>
    request<Surgery>("/theatre/surgeries", { method: "POST", body: JSON.stringify(payload) }),
  rescheduleSurgery: (id: string, payload: Record<string, unknown>) =>
    request<Surgery>(`/theatre/surgeries/${id}/reschedule`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  cancelSurgery: (id: string, reason: string) =>
    request<Surgery>(`/theatre/surgeries/${id}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  /** Record one theatre time. `at` omitted means now. */
  recordTheatreTime: (id: string, milestone: Milestone, at?: string) =>
    request<Surgery>(`/theatre/surgeries/${id}/times`, {
      method: "POST",
      body: JSON.stringify({ milestone, at: at ?? null }),
    }),
  surgerySlip: async (id: string): Promise<Blob> => {
    const response = await fetch(`${API_URL}/api/v1/theatre/surgeries/${id}/slip`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new ApiError(response.status, "The surgery slip could not be printed.");
    }
    return response.blob();
  },

  // -------------------------------------------------------------- leave
  startLeave: (
    admissionId: string,
    payload: { reason: string; expected_return_on?: string | null; bed_retained: boolean }
  ) =>
    request<AdmissionLeave>(`/ipd/admissions/${admissionId}/leave`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  returnFromLeave: (admissionId: string, payload: { bed_id?: string | null; note?: string | null }) =>
    request<AdmissionLeave & { missed_doses_recorded: number }>(`/ipd/admissions/${admissionId}/return`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  roomChargeRuns: () => request<RoomChargeRuns>("/ipd/room-charges/runs"),
  runRoomCharges: () => request<RoomChargeRun>("/ipd/room-charges/run", { method: "POST" }),
  resetPadLayout: (documentType: string, scope: LayoutScope) =>
    request<void>(`/pads/layouts/${documentType}${query({ scope })}`, { method: "DELETE" }).catch((err) => {
      if (err instanceof SyntaxError) return;
      throw err;
    }),

  // ------------------------------------------------------- patient files
  patientFileCategories: () => request<{ items: FileCategoryOption[] }>("/patient-files/categories"),
  patientFiles: (params: {
    patient_id: string;
    admission_id?: string;
    consultation_id?: string;
    pad_document_id?: string;
    include_withdrawn?: boolean;
  }) => request<PatientFileRecord[]>(`/patient-files${query({ ...params })}`),
  uploadPatientFile: async (form: FormData): Promise<PatientFileRecord> => {
    const token = getToken();
    const response = await fetch(`${API_URL}/api/v1/patient-files`, {
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
  patientFileBlob: async (id: string): Promise<Blob> => {
    const response = await fetch(`${API_URL}/api/v1/patient-files/${id}/file`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
      cache: "no-store",
    });
    if (!response.ok) throw new ApiError(response.status, "The file could not be opened.");
    return response.blob();
  },
  withdrawPatientFile: (id: string, reason: string) =>
    request<PatientFileRecord>(`/patient-files/${id}/withdraw`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  // ----------------------------------------------------------- radiology
  radiologyWorklist: (params: { include_reported?: boolean } = {}) =>
    request<{ items: RadiologyWorkItem[] }>(`/pads/radiology/worklist${query({ ...params })}`),

  // --------------------------------------------------------- records file
  recordsChecklist: (admissionId: string) =>
    request<RecordsChecklist>(`/mrd/admissions/${admissionId}/checklist`),
  buildRecords: (admissionId: string, payload: { items: string[]; date_from?: string; date_to?: string }) =>
    request<BundleJob>(`/mrd/admissions/${admissionId}/bundle`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  recordsJob: (jobId: string) => request<BundleJob>(`/mrd/jobs/${jobId}`),
  recordsFile: async (jobId: string): Promise<Blob> => {
    const response = await fetch(`${API_URL}/api/v1/mrd/jobs/${jobId}/file`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
      cache: "no-store",
    });
    if (!response.ok) throw new ApiError(response.status, "The records file could not be opened.");
    return response.blob();
  },

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

  // ------------------------------------------------------------ Visit Pad
  /** The pad for a consultation: its draft, its signed copy, or a new draft. */
  openPad: (consultationId: string, documentType = "opd_visit") =>
    request<PadDocument>(`/pads/consultations/${consultationId}/${documentType}`, {
      method: "POST",
    }),
  /** An inpatient document: the admission's own, or the caller's unfinished note. */
  openAdmissionPad: (admissionId: string, documentType: string, fresh = false) =>
    request<PadDocument>(
      `/pads/admissions/${admissionId}/${documentType}${query({ new: fresh || undefined })}`,
      { method: "POST" }
    ),
  /** A theatre note for one case: its draft, its signed copy, or a new draft. */
  openSurgeryPad: (surgeryId: string, documentType: string) =>
    request<PadDocument>(`/pads/surgeries/${surgeryId}/${documentType}`, { method: "POST" }),
  /** Every document type, with its family (certificate / consent) and requirements. */
  padDocumentTypes: () => request<{ items: PadDocumentTypeInfo[] }>("/pads/document-types"),
  /** The fixed wording a consent form prints. */
  padForm: (documentType: string) => request<FormWording>(`/pads/forms/${documentType}`),
  /** A certificate or consent form, linked to a visit, admission or surgery when given. */
  openPatientPad: (
    patientId: string,
    documentType: string,
    links: {
      consultation_id?: string;
      admission_id?: string;
      surgery_id?: string;
      order_item_id?: string;
      new?: boolean;
    } = {}
  ) =>
    request<PadDocument>(`/pads/patients/${patientId}/${documentType}${query({ ...links })}`, {
      method: "POST",
    }),
  /** The patient's signed paper copy of a consent form has come back. */
  recordPaperSigned: (id: string) =>
    request<PadDocument>(`/pads/documents/${id}/paper-signed`, { method: "POST" }),
  /** Fill a discharge summary's empty sections from the ward record. */
  draftDischargeWithAi: (documentId: string) =>
    request<{ document: PadDocument; filled: string[]; uncertain: string[] }>(
      `/pads/documents/${documentId}/draft-discharge`,
      { method: "POST" }
    ),
  padDocument: (id: string) => request<PadDocument>(`/pads/documents/${id}`),
  padDocuments: (params: {
    patient_id?: string;
    consultation_id?: string;
    admission_id?: string;
    surgery_id?: string;
    document_type?: string;
    include_superseded?: boolean;
  }) => request<PadDocumentSummary[]>(`/pads/documents${query(params)}`),
  savePad: (id: string, values: Record<string, SectionValue>, baseUpdatedAt: string) =>
    request<PadDocument>(`/pads/documents/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ values, base_updated_at: baseUpdatedAt }),
    }),
  arrangePad: (id: string, sections: ArrangementItem[]) =>
    request<PadDocument>(`/pads/documents/${id}/arrangement`, {
      method: "PUT",
      body: JSON.stringify({ sections }),
    }),
  discardPad: (id: string) =>
    request<void>(`/pads/documents/${id}`, { method: "DELETE" }).catch((err) => {
      // 204 has no body, so the JSON parse in `request` throws after success.
      if (err instanceof SyntaxError) return;
      throw err;
    }),
  signPad: (id: string) =>
    request<PadDocument>(`/pads/documents/${id}/sign`, { method: "POST" }),
  amendPad: (id: string, reason: string) =>
    request<PadDocument>(`/pads/documents/${id}/amend`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  padPreviousVisit: (id: string) =>
    request<PadDocument | null>(`/pads/documents/${id}/previous`),
  copyPadFromPrevious: (id: string) =>
    request<PadDocument>(`/pads/documents/${id}/copy-previous`, { method: "POST" }),
  padTemplates: (documentType = "opd_visit") =>
    request<PadTemplate[]>(`/pads/templates${query({ document_type: documentType })}`),
  applyPadTemplate: (id: string, templateId: string, replace: boolean) =>
    request<PadDocument>(`/pads/documents/${id}/apply-template`, {
      method: "POST",
      body: JSON.stringify({ template_id: templateId, replace }),
    }),
  savePadTemplate: (payload: {
    document_id: string;
    name: string;
    description?: string;
    shared: boolean;
  }) =>
    request<PadTemplate>("/pads/templates", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  deletePadTemplate: (id: string) =>
    request<void>(`/pads/templates/${id}`, { method: "DELETE" }).catch((err) => {
      if (err instanceof SyntaxError) return;
      throw err;
    }),
  padCatalogue: (category: string, q: string) =>
    request<CatalogueSuggestion[]>(`/pads/catalogue/${category}${query({ q })}`),
  padLayout: (documentType = "opd_visit") =>
    request<PadLayout>(`/pads/layouts/${documentType}`),
  savePadLayout: (
    documentType: string,
    payload: { scope: LayoutScope; name: string; sections: SectionSpec[] }
  ) =>
    request<PadLayout>(`/pads/layouts/${documentType}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
  /** The PDF, fetched with the session token so it can be opened in a tab. */
  padPdf: async (id: string): Promise<Blob> => {
    const response = await fetch(`${API_URL}/api/v1/pads/documents/${id}/pdf`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
      cache: "no-store",
    });
    if (!response.ok) {
      throw new ApiError(response.status, "This document could not be printed.");
    }
    return response.blob();
  },

  dictationWsUrl: () => `${WS_URL}/api/v1/ws/dictation?token=${encodeURIComponent(getToken() ?? "")}`,

  // -------------------------------------------------------------- laboratory
  labOptions: () => request<LabOptions>("/lab/options"),
  labMasters: (params: { kind?: string; include_inactive?: boolean } = {}) =>
    request<LabMaster[]>(`/lab/masters${query({ ...params })}`),
  saveLabMaster: (payload: Omit<LabMaster, "id">, id?: string) =>
    request<LabMaster>(id ? `/lab/masters/${id}` : "/lab/masters", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    }),
  labTests: (params: { q?: string; include_inactive?: boolean } = {}) =>
    request<LabTest[]>(`/lab/tests${query({ ...params })}`),
  saveLabTest: (payload: Record<string, unknown>, id?: string) =>
    request<LabTest>(id ? `/lab/tests/${id}` : "/lab/tests", {
      method: id ? "PUT" : "POST",
      body: JSON.stringify(payload),
    }),
  /** A doctor confirms the ranges match this laboratory's analyser and kits. */
  reviewLabTest: (id: string) => request<LabTest>(`/lab/tests/${id}/review`, { method: "POST" }),
  pendingLabOrders: () => request<PendingLabOrder[]>("/lab/orders/pending"),
  labRequests: (
    params: {
      q?: string;
      status?: string;
      date_from?: string;
      date_to?: string;
      patient_id?: string;
      admission_id?: string;
      limit?: number;
    } = {}
  ) => request<LabRequestSummary[]>(`/lab/requests${query({ ...params })}`),
  labRequest: (id: string) => request<LabRequest>(`/lab/requests/${id}`),
  labPatientContext: (patientId: string) =>
    request<{ patient: LabPatient; admission: { id: string; ip_number: string; billable: boolean } | null }>(
      `/lab/patients/${patientId}/context`
    ),
  registerLab: (payload: Record<string, unknown>) =>
    request<LabRequest>("/lab/requests", { method: "POST", body: JSON.stringify(payload) }),
  collectLabSample: (id: string) => request<LabRequest>(`/lab/requests/${id}/collect`, { method: "POST" }),
  billLabRequest: (id: string, payload: { billing: string; admission_id?: string | null }) =>
    request<LabRequest>(`/lab/requests/${id}/bill`, { method: "POST", body: JSON.stringify(payload) }),
  cancelLab: (id: string, payload: { reason: string; item_ids?: string[] | null }) =>
    request<LabRequest>(`/lab/requests/${id}/cancel`, { method: "POST", body: JSON.stringify(payload) }),
  saveLabResults: (itemId: string, payload: Record<string, unknown>) =>
    request<LabRequest>(`/lab/items/${itemId}/results`, { method: "POST", body: JSON.stringify(payload) }),
  verifyLabResult: (itemId: string, criticalNote?: string | null) =>
    request<LabRequest>(`/lab/items/${itemId}/verify`, {
      method: "POST",
      body: JSON.stringify({ critical_note: criticalNote ?? null }),
    }),
  reopenLabResult: (itemId: string, reason: string) =>
    request<LabRequest>(`/lab/items/${itemId}/reopen`, { method: "POST", body: JSON.stringify({ reason }) }),
  /** Suggested values from an analyser printout. Nothing is saved. */
  readLabPrintout: async (itemId: string, file: File): Promise<PrintoutReading> => {
    const form = new FormData();
    form.append("file", file);
    const token = getToken();
    const response = await fetch(`${API_URL}/api/v1/lab/items/${itemId}/printout`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
    if (!response.ok) {
      let detail = `The printout could not be read (${response.status})`;
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
  labReportPdf: async (id: string): Promise<Blob> => {
    const response = await fetch(`${API_URL}/api/v1/lab/requests/${id}/report`, {
      headers: { Authorization: `Bearer ${getToken() ?? ""}` },
      cache: "no-store",
    });
    if (!response.ok) {
      let detail = "The report could not be printed.";
      try {
        const body = await response.json();
        if (typeof body.detail === "string") detail = body.detail;
      } catch {
        /* keep default */
      }
      throw new ApiError(response.status, detail);
    }
    return response.blob();
  },
  patientLabResults: (patientId: string, admissionId?: string) =>
    request<PatientLabResult[]>(`/lab/patients/${patientId}/results${query({ admission_id: admissionId })}`),

  // ------------------------------------------------------------ staff accounts
  staffRoles: () => request<StaffRole[]>("/users/roles"),

  staffUsers: () => request<User[]>("/users"),

  createStaffUser: (payload: {
    email: string;
    full_name: string;
    password: string;
    role: User["role"];
    department?: string | null;
  }) => request<User>("/users", { method: "POST", body: JSON.stringify(payload) }),

  updateStaffUser: (id: string, payload: Record<string, unknown>) =>
    request<User>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  resetStaffPassword: (id: string, password: string) =>
    request<void>(`/users/${id}/password`, {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

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
