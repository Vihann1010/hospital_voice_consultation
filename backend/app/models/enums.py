import enum


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    STAFF = "staff"


class Department(str, enum.Enum):
    ORTHOPEDICS = "orthopedics"
    GYNECOLOGY = "gynecology"


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class ConsultationStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TurnRole(str, enum.Enum):
    PATIENT = "patient"
    ASSISTANT = "assistant"


class InvestigationCategory(str, enum.Enum):
    BLOOD = "blood"
    URINE = "urine"
    XRAY = "xray"
    MRI = "mri"
    CT = "ct"
    ULTRASOUND = "ultrasound"
    DEXA = "dexa"
    ORTHOPEDIC = "orthopedic"
    GYNECOLOGY = "gynecology"
    HORMONAL = "hormonal"
    TUMOR_MARKERS = "tumor_markers"


class InvestigationPriority(str, enum.Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    STAT = "stat"


class OrderStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PARTIALLY_REPORTED = "partially_reported"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ReportStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    ANALYZED = "analyzed"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class AbnormalFlag(str, enum.Enum):
    NORMAL = "normal"
    LOW = "low"
    HIGH = "high"
    CRITICAL_LOW = "critical_low"
    CRITICAL_HIGH = "critical_high"
    ABNORMAL = "abnormal"       # qualitative result outside expected
    UNKNOWN = "unknown"


class PrescriptionStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    CANCELLED = "cancelled"


class DeliveryChannel(str, enum.Enum):
    WHATSAPP = "whatsapp"
    SMS = "sms"
    EMAIL = "email"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuditAction(str, enum.Enum):
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    VIEW_PATIENT = "view_patient"
    VIEW_CONSULTATION = "view_consultation"
    CREATE_ORDER = "create_order"
    UPLOAD_REPORT = "upload_report"
    VIEW_REPORT = "view_report"
    CREATE_PRESCRIPTION = "create_prescription"
    SEND_PRESCRIPTION = "send_prescription"
    REVIEW_CONSULTATION = "review_consultation"
    COPILOT_DECISION = "copilot_decision"
    EXPORT_DOCUMENT = "export_document"
    PERMISSION_DENIED = "permission_denied"


class VisitType(str, enum.Enum):
    NEW = "new"
    FOLLOW_UP = "follow_up"
    REVIEW = "review"
    PROCEDURE = "procedure"


class VisitStatus(str, enum.Enum):
    REGISTERED = "registered"       # billed at reception, waiting
    IN_CONSULTATION = "in_consultation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ServiceCategory(str, enum.Enum):
    CONSULTATION = "consultation"
    PROCEDURE = "procedure"
    INVESTIGATION = "investigation"
    REGISTRATION = "registration"
    OTHER = "other"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentMode(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    NET_BANKING = "net_banking"
    INSURANCE = "insurance"
    WAIVER = "waiver"


class PayerType(str, enum.Enum):
    SELF_PAY = "self_pay"
    INSURANCE = "insurance"
    TPA = "tpa"
    CORPORATE = "corporate"
    GOVERNMENT_SCHEME = "government_scheme"


class ClaimStatus(str, enum.Enum):
    DRAFT = "draft"
    PRE_AUTH_REQUESTED = "pre_auth_requested"
    PRE_AUTH_APPROVED = "pre_auth_approved"
    PRE_AUTH_REJECTED = "pre_auth_rejected"
    SUBMITTED = "submitted"
    QUERIED = "queried"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    REJECTED = "rejected"
    SETTLED = "settled"


class CashSessionStatus(str, enum.Enum):
    OPEN = "open"
    CLOSED = "closed"
    RECONCILED = "reconciled"

class WardType(str, enum.Enum):
    GENERAL = "general"
    SEMI_PRIVATE = "semi_private"
    PRIVATE = "private"
    DELUXE = "deluxe"
    ICU = "icu"
    HDU = "hdu"
    NICU = "nicu"
    LABOUR = "labour"
    POST_OPERATIVE = "post_operative"
    DAY_CARE = "day_care"


class BedStatus(str, enum.Enum):
    VACANT = "vacant"
    OCCUPIED = "occupied"
    # A bed is not available the moment a patient leaves it.
    CLEANING = "cleaning"
    BLOCKED = "blocked"
    MAINTENANCE = "maintenance"


class AdmissionType(str, enum.Enum):
    PLANNED = "planned"
    EMERGENCY = "emergency"
    TRANSFER_IN = "transfer_in"
    DAY_CARE = "day_care"
    MATERNITY = "maternity"


class AdmissionStatus(str, enum.Enum):
    ADMITTED = "admitted"
    # The doctor has written the patient up for discharge, but the bill is
    # not settled and the bed is not yet free.
    DISCHARGE_INITIATED = "discharge_initiated"
    DISCHARGED = "discharged"
    CANCELLED = "cancelled"


class DischargeType(str, enum.Enum):
    ROUTINE = "routine"
    AGAINST_MEDICAL_ADVICE = "against_medical_advice"
    TRANSFERRED_OUT = "transferred_out"
    ABSCONDED = "absconded"
    DEATH = "death"


class ChargeCategory(str, enum.Enum):
    BED = "bed"
    NURSING = "nursing"
    DOCTOR_VISIT = "doctor_visit"
    PROCEDURE = "procedure"
    INVESTIGATION = "investigation"
    MEDICINE = "medicine"
    CONSUMABLE = "consumable"
    OXYGEN = "oxygen"
    OTHER = "other"


class MedicationRouteIPD(str, enum.Enum):
    ORAL = "oral"
    IV = "iv"
    IM = "im"
    SC = "sc"
    TOPICAL = "topical"
    INHALED = "inhaled"
    RECTAL = "rectal"
    SUBLINGUAL = "sublingual"
    NASOGASTRIC = "nasogastric"


class MedicationStatus(str, enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    STOPPED = "stopped"
    HELD = "held"


class NoteType(str, enum.Enum):
    ADMISSION = "admission"
    DOCTOR_ROUND = "doctor_round"
    NURSING = "nursing"
    PROGRESS = "progress"
    PROCEDURE = "procedure"
    HANDOVER = "handover"
    DISCHARGE_SUMMARY = "discharge_summary"
