import enum


class UserRole(str, enum.Enum):
    """Staff roles, named as the hospital names them.

    Separating manager from supervisor from reception is what stops the three
    distinct kinds of elevated authority — seeing hospital revenue, giving
    money back, and holding clinical responsibility — from collapsing into one
    another, which is what happens when every privileged action is simply
    "not reception".
    """

    ADMIN = "admin"
    MANAGER = "manager"
    DOCTOR = "doctor"
    SUPERVISOR = "supervisor"
    RECEPTION = "reception"
    # Charts observations and doses, and writes and signs the nursing
    # documents. No prescribing, no admitting or discharging, no till.
    NURSE = "nurse"
    # The laboratory bench: registers samples and enters results. Verifying
    # a result is the pathologist's, who is a doctor.
    LAB = "lab"


class Department(str, enum.Enum):
    """The clinical departments this installation runs.

    Adding a member here is only half the work: every department must also be
    configured in ``app.departments`` (intake guide, red flags, slots, labels),
    and the application refuses to start until it is. A department that exists
    as an enum value but has no clinical content would screen no red flags and
    silently hand the patient another speciality's intake questions.
    """

    ORTHOPEDICS = "orthopedics"
    GYNECOLOGY = "gynecology"
    GASTROENTEROLOGY = "gastroenterology"


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


class DocumentKind(str, enum.Enum):
    """What a patient handed over, as declared at upload and re-checked in code.

    The kind decides which analyser runs, and the analysers are not
    interchangeable. Reading a prescription with the laboratory parser is what
    turned the dose notation "PAN 40 MG 1-0-0" into an analyte called PAN
    measuring 40 against a reference range of 1.0 to 0.0, flagged HIGH.
    """

    PRESCRIPTION = "prescription"
    LAB_REPORT = "lab_report"
    IMAGING = "imaging"
    OTHER = "other"


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
    # Who was given access to the system, and who changed what someone may do,
    # is itself sensitive: it is the trail that explains every other entry.
    USER_CREATE = "user_create"
    USER_UPDATE = "user_update"
    WALLET_DEPOSIT = "wallet_deposit"
    WALLET_WITHDRAWAL = "wallet_withdrawal"
    # Undoing counter work is the trail an auditor follows first, so each
    # step of the cascade is recorded under its own name rather than all of
    # them sharing a generic "correction".
    RECEIPT_CANCEL = "receipt_cancel"
    # Money actually given back, and a bill struck. Both were recorded as
    # "export_document" before, which made a refund impossible to find.
    REFUND_ISSUE = "refund_issue"
    INVOICE_CANCEL = "invoice_cancel"
    INVOICE_UNCANCEL = "invoice_uncancel"
    INVOICE_AMEND = "invoice_amend"
    VISIT_CANCEL = "visit_cancel"
    VISIT_UNCANCEL = "visit_uncancel"
    APPOINTMENT_BOOK = "appointment_book"
    APPOINTMENT_CANCEL = "appointment_cancel"
    # The clinical record. A signature, and every correction made to a signed
    # document, is the trail a medico-legal inquiry reads first.
    PAD_SIGN = "pad_sign"
    PAD_AMEND = "pad_amend"
    PAD_LAYOUT_CHANGE = "pad_layout_change"
    # The operation theatre: a booking, a cancellation, each theatre time.
    SURGERY_BOOK = "surgery_book"
    SURGERY_CANCEL = "surgery_cancel"
    SURGERY_TIME = "surgery_time"
    # The patient's signed paper copy of a consent form was received.
    CONSENT_PAPER_SIGNED = "consent_paper_signed"
    # A file attached to, or withdrawn from, a patient's record.
    FILE_UPLOAD = "file_upload"
    FILE_WITHDRAW = "file_withdraw"
    # A patient going on leave from the ward, and coming back.
    LEAVE_START = "leave_start"
    LEAVE_RETURN = "leave_return"
    # Room charges posted by hand, outside the morning run.
    ROOM_CHARGES_RUN = "room_charges_run"
    # The laboratory: tests registered, a result verified, a verified result
    # reopened for correction, and tests cancelled.
    LAB_REGISTER = "lab_register"
    LAB_VERIFY = "lab_verify"
    LAB_REOPEN = "lab_reopen"
    LAB_CANCEL = "lab_cancel"
    # A diet ordered for an inpatient, and a diet order stopped.
    DIET_ORDER = "diet_order"
    DIET_STOP = "diet_stop"
    # The books: a manual voucher, a reversal, a posting run, and payouts.
    VOUCHER_CREATE = "voucher_create"
    VOUCHER_REVERSE = "voucher_reverse"
    BOOKS_POSTING_RUN = "books_posting_run"
    PAYOUT_APPROVE = "payout_approve"
    PAYOUT_PAY = "payout_pay"
    PAYOUT_CANCEL = "payout_cancel"
    PAYOUT_TERMS = "payout_terms"
    # TPA and insurance: a policy saved, a claim opened or moved, its share put
    # on or taken off the bill, and a payer's settlement recorded or cancelled.
    POLICY_SAVE = "policy_save"
    CLAIM_CREATE = "claim_create"
    CLAIM_STATUS = "claim_status"
    CLAIM_BOOK = "claim_book"
    CLAIM_UNBOOK = "claim_unbook"
    CLAIM_SETTLE = "claim_settle"
    CLAIM_SETTLE_CANCEL = "claim_settle_cancel"
    # A consultant added to the register or changed.
    CONSULTANT_SAVE = "consultant_save"


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


class AppointmentStatus(str, enum.Enum):
    """The queue board's colours, carried over from the old system.

    Five states rather than six: the old board showed both "engaged" and
    "with the doctor", which named the same fact — the patient is in the
    room — from the clerk's side and the doctor's. One state, labelled
    "With the doctor" on screen, avoids two ways to record the same thing
    and the disagreements that follow.
    """

    PENDING = "pending"        # booked, not yet arrived
    WAITING = "waiting"        # arrived and registered, sitting outside
    ENGAGED = "engaged"        # in the room
    DONE = "done"
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
    CHEQUE = "cheque"
    INSURANCE = "insurance"
    WAIVER = "waiver"
    # Money the patient already handed over, sitting in their wallet. It is a
    # payment against the bill but NOT a collection: counting it in the day's
    # takings would bank the same rupee twice, once on deposit and once on
    # use. Every collection figure filters this mode out for that reason.
    WALLET = "wallet"


class WalletEntryKind(str, enum.Enum):
    """Why a patient's balance moved.

    Kept as a named reason rather than inferred from the sign, because
    "money in" covers both an advance the patient chose to leave and a refund
    they were owed, and the two answer different questions at closing time.
    """

    DEPOSIT = "deposit"              # advance handed over at the counter
    REFUND_CREDIT = "refund_credit"  # a bill refund left on account
    APPLIED = "applied"              # spent against an invoice
    WITHDRAWAL = "withdrawal"        # paid back out to the patient
    # Opening balances brought across from the old system, and corrections.
    ADJUSTMENT = "adjustment"


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


class PadStatus(str, enum.Enum):
    """Where a clinical document stands.

    There is no "edited" state. A signed document is corrected by signing a
    new version, which marks this one superseded and keeps it readable.
    """

    DRAFT = "draft"
    SIGNED = "signed"
    SUPERSEDED = "superseded"


class PatientFileCategory(str, enum.Enum):
    """What a file on a patient's record is."""

    IDENTITY_PROOF = "identity_proof"
    REFERRAL_LETTER = "referral_letter"
    PREVIOUS_RECORDS = "previous_records"
    OUTSIDE_INVESTIGATION = "outside_investigation"
    SIGNED_CONSENT = "signed_consent"
    CLINICAL_PHOTOGRAPH = "clinical_photograph"
    INSURANCE = "insurance"
    OTHER = "other"


class SurgeryStatus(str, enum.Enum):
    """Where a surgical case stands. It only moves forward."""

    SCHEDULED = "scheduled"
    IN_THEATRE = "in_theatre"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class NoteType(str, enum.Enum):
    ADMISSION = "admission"
    DOCTOR_ROUND = "doctor_round"
    NURSING = "nursing"
    PROGRESS = "progress"
    PROCEDURE = "procedure"
    HANDOVER = "handover"
    DISCHARGE_SUMMARY = "discharge_summary"
