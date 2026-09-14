"""Import every model so Base.metadata knows the full schema."""
from app.db.base import Base
from app.models.appointment import Appointment
from app.models.audit import AuditLog
from app.models.consultant import Consultant, ReferralProvider
from app.models.consultation import Consultation, ConversationTurn
from app.models.pad import PadCatalogueEntry, PadDocument, PadLayout, PadTemplate
from app.models.theatre import Operation, Surgery, TheatreRoom
from app.models.patient_file import PatientFile  # noqa: F401
from app.models.admission_leave import AdmissionLeave  # noqa: F401
from app.models.job_run import JobRun  # noqa: F401
from app.models.lab import LabMaster, LabParameter, LabRequest, LabRequestItem, LabTest  # noqa: F401
from app.models.investigation import (
    DoctorFavoriteInvestigation,
    InvestigationOrder,
    InvestigationOrderItem,
    InvestigationReport,
    InvestigationTemplate,
)
from app.models.emr import (
    CashSession,
    DocumentCounter,
    InsuranceClaim,
    InsurancePolicy,
    Invoice,
    InvoiceLine,
    PatientWallet,
    Payment,
    ServiceItem,
    Visit,
    WalletEntry,
)
from app.models.ipd import (
    Admission,
    AdmissionCharge,
    Bed,
    BedOccupancy,
    ClinicalNote,
    MedicationAdministration,
    MedicationOrder,
    VitalsRecord,
    Ward,
)
from app.models.organisation import NegotiatedRate, Organisation
from app.models.patient import Patient, PatientFieldSetting
from app.models.printing import PrintSetting
from app.models.reporting import ReportColumnSetting
from app.models.prescription import (
    MessageDelivery,
    Prescription,
    PrescriptionMedicine,
)
from app.models.user import User

__all__ = [
    "Base",
    "User",
    "Patient",
    "PatientFieldSetting",
    "Consultant",
    "ReferralProvider",
    "Organisation",
    "NegotiatedRate",
    "Consultation",
    "ConversationTurn",
    "InvestigationOrder",
    "InvestigationOrderItem",
    "InvestigationReport",
    "DoctorFavoriteInvestigation",
    "InvestigationTemplate",
    "Prescription",
    "PrescriptionMedicine",
    "MessageDelivery",
    "PrintSetting",
    "ReportColumnSetting",
    "AuditLog",
    "Appointment",
    "DocumentCounter",
    "ServiceItem",
    "Visit",
    "Invoice",
    "InvoiceLine",
    "Payment",
    "CashSession",
    "PatientWallet",
    "WalletEntry",
    "InsurancePolicy",
    "InsuranceClaim",
    "Ward",
    "Bed",
    "Admission",
    "BedOccupancy",
    "AdmissionCharge",
    "VitalsRecord",
    "MedicationOrder",
    "MedicationAdministration",
    "ClinicalNote",
]
