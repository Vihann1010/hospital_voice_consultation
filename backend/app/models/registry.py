"""Import every model so Base.metadata knows the full schema."""
from app.db.base import Base
from app.models.audit import AuditLog
from app.models.consultation import Consultation, ConversationTurn
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
    Payment,
    ServiceItem,
    Visit,
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
from app.models.patient import Patient
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
    "AuditLog",
    "DocumentCounter",
    "ServiceItem",
    "Visit",
    "Invoice",
    "InvoiceLine",
    "Payment",
    "CashSession",
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
