"""The v1 API surface.

Two kinds of router are included here. The core ones are what every
installation has: registering a patient, billing, consulting, prescribing,
ordering an investigation. The optional ones belong to a module, and are
included only when this installation runs that module — so a clinic with no
ward does not merely hide the ward board, it does not serve /ipd at all.

Registering the router is the enforcement point. Anything softer — hiding a
link, checking a flag inside each handler — leaves the endpoint answering to
whoever types the URL, and leaves a dozen handlers to remember the check.
"""
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
from app.core.config import settings
from app.core.logging import get_logger
from app.modules import Module
from app.ws import consultation_ws, dictation_ws

logger = get_logger(__name__)

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
api_router.include_router(reports.router)
api_router.include_router(masters.router)
api_router.include_router(pads.router)
api_router.include_router(patient_files.router)
api_router.include_router(mrd.router)
api_router.include_router(users.router)
api_router.include_router(public_documents.router)
api_router.include_router(consultation_ws.router)
api_router.include_router(dictation_ws.router)

# Optional modules. ipd_advance rides with ipd: taking an advance against an
# admission has no meaning without admissions.
_MODULE_ROUTERS = {
    Module.IPD: (ipd.router, ipd_advance.router),
    Module.LABORATORY: (lab.router,),
    Module.DIET: (diet.router,),
    Module.THEATRE: (theatre.router,),
    Module.INSURANCE: (insurance.router,),
}

_enabled = settings.enabled_modules
for _module, _routers in _MODULE_ROUTERS.items():
    if _module in _enabled:
        for _router in _routers:
            api_router.include_router(_router)

logger.info(
    "api_modules_registered",
    extra={
        "enabled": sorted(m.value for m in _enabled),
        "disabled": sorted(m.value for m in Module if m not in _enabled),
    },
)
