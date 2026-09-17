from fastapi import APIRouter

from app.api.v1.routes import (
    accounts,
    appointments,
    auth,
    consultations,
    finance,
    health,
    insurance,
    investigations,
    ipd,
    ipd_advance,
    diet,
    lab,
    masters,
    pads,
    theatre,
    patient_files,
    mrd,
    patient_uploads,
    patients,
    prescriptions,
    reception,
    reports,
    upload_links,
    users,
    public_documents,
)
from app.ws import consultation_ws, dictation_ws

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(consultations.router)
api_router.include_router(patients.router)
api_router.include_router(patient_uploads.router)
api_router.include_router(upload_links.router)
api_router.include_router(investigations.router)
api_router.include_router(prescriptions.router)
api_router.include_router(reception.router)
api_router.include_router(appointments.router)
api_router.include_router(finance.router)
api_router.include_router(accounts.router)
api_router.include_router(insurance.router)
api_router.include_router(reports.router)
api_router.include_router(ipd.router)
api_router.include_router(ipd_advance.router)
api_router.include_router(masters.router)
api_router.include_router(pads.router)
api_router.include_router(theatre.router)
api_router.include_router(lab.router)
api_router.include_router(diet.router)
api_router.include_router(patient_files.router)
api_router.include_router(mrd.router)
api_router.include_router(users.router)
api_router.include_router(public_documents.router)
api_router.include_router(consultation_ws.router)
api_router.include_router(dictation_ws.router)
