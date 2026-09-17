"""Scan-to-upload: a QR code the nurse shows, a phone that answers it.

The patient is sitting in the intake room with a bag of old prescriptions and
lab reports. The alternatives are photocopying them at the desk, or the
doctor reading them across a table mid-consultation. This gives the nurse a
code to hold up: the patient photographs it and the reports arrive on the
record before the doctor opens it.

**The QR is rendered here, not in the browser.** It encodes a capability, and
a capability assembled in JavaScript is one that has to be handled by every
screen that shows it. One endpoint returns the image and nothing else knows
the token's shape.

**It expires in minutes, not hours.** A code displayed on a screen in a room
full of waiting patients is a code that can be photographed by the wrong
person. See `create_upload_token` for why that shapes the lifetime.
"""
import base64
import io
import uuid
from datetime import timedelta
from typing import Annotated

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.api.deps import CurrentUser, get_consultation_service, require_permission
from app.core.clock import local_now
from app.core.config import settings
from app.core.logging import get_logger
from app.core.permissions import Permission
from app.core.security import create_upload_token
from app.services.consultation_service import ConsultationService

logger = get_logger(__name__)
router = APIRouter(prefix="/upload-links", tags=["patient"])

Service = Annotated[ConsultationService, Depends(get_consultation_service)]

# Whoever runs the intake can offer the code. It is the same authority as
# uploading a report on the patient's behalf, which is what it delegates.
ISSUE_LINK = require_permission(Permission.REPORT_UPLOAD)


class UploadLinkOut(BaseModel):
    consultation_id: uuid.UUID
    #: What the QR encodes. Also shown as text, because a phone camera that
    #: will not focus is a real thing in a hospital corridor.
    url: str
    token: str
    expires_in_minutes: int
    expires_at: str
    #: A data URI of the QR, so the screen can render it with no library and
    #: no second request.
    qr_data_uri: str
    #: True when the configured public address is one a phone cannot reach.
    unreachable_warning: bool


def _qr_data_uri(url: str) -> str:
    code = qrcode.QRCode(
        version=None,
        # A phone camera in a hospital corridor is not a scanner: medium
        # correction lets the code survive glare and an off-angle shot.
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    code.add_data(url)
    code.make(fit=True)
    image = code.make_image(fill_color="#0B55A1", back_color="white")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _is_unreachable(base: str) -> bool:
    """Would a phone fail to open this address?

    `localhost` resolves to the phone itself, so a QR pointing there opens
    nothing and looks like a broken feature. Worth saying plainly on the
    screen rather than leaving the nurse to discover it with a patient
    waiting.
    """
    lowered = (base or "").lower()
    return "localhost" in lowered or "127.0.0.1" in lowered


@router.post("/{consultation_id}", response_model=UploadLinkOut,
             dependencies=[Depends(ISSUE_LINK)])
async def create_upload_link(
    consultation_id: uuid.UUID, service: Service, user: CurrentUser
) -> UploadLinkOut:
    """Mint a QR code for this consultation's phone uploads."""
    consultation = await service.consultations.get(consultation_id)
    if consultation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Consultation not found")

    token = create_upload_token(
        consultation_id=consultation_id, patient_id=consultation.patient_id
    )
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    url = f"{base}/upload/{token}"
    expires_at = local_now() + timedelta(minutes=settings.UPLOAD_TOKEN_EXPIRE_MINUTES)

    logger.info(
        "upload_link_issued",
        extra={"consultation_id": str(consultation_id), "issued_by": user.full_name},
    )
    return UploadLinkOut(
        consultation_id=consultation_id,
        url=url,
        token=token,
        expires_in_minutes=settings.UPLOAD_TOKEN_EXPIRE_MINUTES,
        expires_at=expires_at.isoformat(),
        qr_data_uri=_qr_data_uri(url),
        unreachable_warning=_is_unreachable(base),
    )
