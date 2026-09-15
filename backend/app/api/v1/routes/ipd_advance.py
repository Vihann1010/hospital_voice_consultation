"""Taking an advance from an inpatient's family during the stay.

A real collection: it gets a receipt from the same series as every other
payment, it lands in the patient's wallet tagged to this admission, and the
final bill is settled from it. Taking money is counter authority, whoever is
standing at the bedside.
"""
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import CurrentUser, DbSession, require_permission
from app.core.audit import client_ip, record as audit_record
from app.core.permissions import Permission
from app.models.enums import AuditAction, PaymentMode
from app.models.ipd import Admission
from app.services.ipd_service import IPDError, IPDService

router = APIRouter(prefix="/ipd", tags=["ipd"])

COLLECT = require_permission(Permission.PAYMENT_COLLECT)


class AdvanceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_paise: int = Field(gt=0)
    mode: PaymentMode = PaymentMode.CASH
    mode_details: Optional[Dict[str, Any]] = None


@router.post("/admissions/{admission_id}/advance", status_code=201, dependencies=[Depends(COLLECT)])
async def take_advance(
    admission_id: uuid.UUID, payload: AdvanceIn, session: DbSession, user: CurrentUser, request: Request
) -> Dict[str, Any]:
    service = IPDService(session)
    try:
        entry = await service.take_advance(
            admission_id, amount_paise=payload.amount_paise, mode=payload.mode.value,
            mode_details=payload.mode_details, received_by_name=user.full_name,
        )
        await session.commit()
    except IPDError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    admission = await session.get(Admission, admission_id)
    await audit_record(
        AuditAction.WALLET_DEPOSIT,
        actor_id=user.id, actor_name=user.full_name, actor_role=user.role.value,
        entity_type="wallet_entry", entity_id=entry.id, patient_id=entry.patient_id,
        ip_address=client_ip(request),
        detail={"receipt": entry.receipt_number, "amount_paise": payload.amount_paise,
                "mode": payload.mode.value, "ip_number": admission.ip_number if admission else None},
    )
    return {
        "entry": {"id": entry.id, "receipt_number": entry.receipt_number, "amount_paise": entry.amount_paise,
                  "balance_after_paise": entry.balance_after_paise, "created_at": entry.created_at},
        "bill": await service.running_bill(admission_id),
    }
