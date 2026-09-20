"""A completed day case bills to its visit, and bills once.

The inpatient path posts the theatre charge to the admission's running bill
without anyone confirming it. A clinic has no admission, and until now every
case ended with "bill it at the counter" — which in a clinic where every case
is a day case means every procedure depends on someone remembering.

Needs a real database: this exercises pricing, invoice numbering and the
nested transaction the charge is raised in, none of which can be faked
usefully.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


async def _fixtures(session):
    from app.core.clock import local_today
    from app.models.emr import ServiceItem, Visit
    from app.models.enums import Department, Gender, ServiceCategory, UserRole
    from app.models.patient import Patient
    from app.models.theatre import Operation
    from app.models.user import User

    patient = Patient(name="Day Case Patient", age=52, gender=Gender.MALE,
                      phone_number="9800000101")
    session.add(patient)
    await session.flush()

    suffix = uuid.uuid4().hex[:6].upper()
    service = ServiceItem(
        code=f"OGD{suffix}", name="Upper GI Endoscopy", rate_paise=250000,
        category=ServiceCategory.PROCEDURE,
    )
    operation = Operation(
        code=f"OP{suffix}", name="Upper GI Endoscopy",
        department=Department.GASTROENTEROLOGY, default_minutes=15,
        service_code=service.code,
    )
    visit = Visit(
        visit_number=f"V{suffix}", patient_id=patient.id,
        department=Department.GASTROENTEROLOGY, visit_date=local_today(),
    )
    user = User(
        email=f"endo{suffix}@example.test", full_name="Dr Endoscopist",
        hashed_password="x", role=UserRole.DOCTOR,
        department=Department.GASTROENTEROLOGY,
    )
    session.add_all([service, operation, visit, user])
    await session.flush()
    return patient, visit, operation, user


async def _book_and_complete(session, patient, visit, operation, user):
    from app.services.theatre_service import TheatreService

    service = TheatreService(session)
    surgery = await service.book(
        {
            "patient_id": patient.id,
            "visit_id": visit.id,
            "operation_id": operation.id,
            "laterality": "Not applicable",
            "scheduled_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            "priority": "emergency",  # skips the checklist, which is its own test
            "surgeon_name": "Dr Endoscopist",
            "anaesthesia_type": "Sedation",
        },
        user=user,
    )
    now = datetime.now(timezone.utc)
    await service.record_time(surgery.id, milestone="wheel_in_at", at=now, user=user)
    return surgery, await service.record_time(
        surgery.id, milestone="wheel_out_at", at=now + timedelta(minutes=12), user=user
    )


async def test_a_completed_day_case_raises_a_bill_on_the_visit(session):
    from sqlalchemy import select

    from app.models.emr import Invoice

    patient, visit, operation, user = await _fixtures(session)
    surgery, result = await _book_and_complete(session, patient, visit, operation, user)

    assert surgery.charge_reference, "the procedure was not billed"
    assert "counter" in (result["charge_note"] or "").lower()

    invoices = (
        await session.execute(select(Invoice).where(Invoice.visit_id == visit.id))
    ).scalars().all()
    assert len(invoices) == 1
    assert invoices[0].invoice_number == surgery.charge_reference
    # Raised, not paid: the counter still takes the money and gives the receipt.
    assert invoices[0].status.value == "issued"


async def test_the_bill_is_not_raised_twice(session):
    """Correcting a wheel-out time must not charge the patient again."""
    from sqlalchemy import select

    from app.models.emr import Invoice
    from app.services.theatre_service import TheatreService

    patient, visit, operation, user = await _fixtures(session)
    surgery, _ = await _book_and_complete(session, patient, visit, operation, user)
    first = surgery.charge_reference

    await TheatreService(session).record_time(
        surgery.id, milestone="wheel_out_at",
        at=datetime.now(timezone.utc) + timedelta(minutes=20), user=user,
    )
    invoices = (
        await session.execute(select(Invoice).where(Invoice.visit_id == visit.id))
    ).scalars().all()
    assert len(invoices) == 1
    assert surgery.charge_reference == first


async def test_a_case_with_neither_admission_nor_visit_says_so(session):
    """No silent free procedure: it is reported so the counter can pick it up."""
    from app.services.theatre_service import TheatreService

    patient, visit, operation, user = await _fixtures(session)
    service = TheatreService(session)
    surgery = await service.book(
        {
            "patient_id": patient.id,
            "operation_id": operation.id,
            "laterality": "Not applicable",
            "scheduled_at": datetime.now(timezone.utc) + timedelta(minutes=5),
            "priority": "emergency",
            "surgeon_name": "Dr Endoscopist",
        },
        user=user,
    )
    now = datetime.now(timezone.utc)
    await service.record_time(surgery.id, milestone="wheel_in_at", at=now, user=user)
    result = await service.record_time(
        surgery.id, milestone="wheel_out_at", at=now + timedelta(minutes=10), user=user
    )
    assert surgery.charge_reference is None
    assert "counter" in result["charge_note"].lower()


async def test_a_case_cannot_be_billed_to_both_an_admission_and_a_visit(session):
    from app.services.theatre_service import TheatreError, TheatreService

    patient, visit, operation, user = await _fixtures(session)
    with pytest.raises(TheatreError):
        await TheatreService(session).book(
            {
                "patient_id": patient.id,
                "visit_id": visit.id,
                "admission_id": uuid.uuid4(),
                "operation_id": operation.id,
                "laterality": "Not applicable",
                "scheduled_at": datetime.now(timezone.utc) + timedelta(minutes=5),
                "surgeon_name": "Dr Endoscopist",
            },
            user=user,
        )
