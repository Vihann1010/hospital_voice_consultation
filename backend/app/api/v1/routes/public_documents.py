"""Unauthenticated, signed document access.

Messaging providers such as Twilio fetch media anonymously, so these links
cannot require a bearer token. Each link is scoped to one prescription, signed
with the application secret and expires, and the QR verification endpoint
returns only what a pharmacist needs to confirm a sheet is genuine — never the
full clinical record.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.api.deps import get_prescription_service
from app.services.prescription_service import PrescriptionService

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/prescriptions/{prescription_id}/pdf")
async def signed_prescription_pdf(
    prescription_id: uuid.UUID,
    token: str = Query(..., description="Signed, expiring access token"),
    service: PrescriptionService = Depends(get_prescription_service),
) -> FileResponse:
    if not PrescriptionService.verify_document_token(prescription_id, token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This link is invalid or has expired")
    found = await service.pdf_bytes(prescription_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Prescription PDF not found")
    path, filename = found
    return FileResponse(path, media_type="application/pdf", filename=filename)


@router.get("/prescriptions/verify/{prescription_number}")
async def verify_prescription(
    prescription_number: str,
    service: PrescriptionService = Depends(get_prescription_service),
) -> dict:
    """QR target. Confirms authenticity without exposing clinical detail."""
    prescription = await service.get_by_number(prescription_number)
    if prescription is None:
        return {"valid": False, "message": "No prescription found with this reference."}
    return {
        "valid": prescription.status.value == "issued",
        "prescription_number": prescription.prescription_number,
        "status": prescription.status.value,
        "issued_on": prescription.issued_at.isoformat() if prescription.issued_at else None,
        "doctor": prescription.doctor_name,
        "department": prescription.department.value,
        "hospital": "Satya Hospital, Kanpur",
        "medicine_count": len(prescription.medicines),
    }
