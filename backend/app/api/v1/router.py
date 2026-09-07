from fastapi import APIRouter

from app.api.v1.routes import (
    auth,
    consultations,
    finance,
    health,
    investigations,
    ipd,
    patient_uploads,
    patients,
    prescriptions,
    reception,
    public_documents,
)
from app.ws import consultation_ws, dictation_ws

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(consultations.router)
api_router.include_router(patients.router)
api_router.include_router(patient_uploads.router)
api_router.include_router(investigations.router)
api_router.include_router(prescriptions.router)
api_router.include_router(reception.router)
api_router.include_router(finance.router)
api_router.include_router(ipd.router)
api_router.include_router(public_documents.router)
api_router.include_router(consultation_ws.router)
api_router.include_router(dictation_ws.router)
