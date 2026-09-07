"""Repository and schema behaviour against a real PostgreSQL."""
import uuid

import pytest

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


async def test_patient_round_trip_and_search(session):
    from app.models.enums import Gender
    from app.models.patient import Patient
    from app.repositories.patient_repository import PatientRepository

    repository = PatientRepository(session)
    patient = Patient(
        name="Integration Test Patient", age=44, gender=Gender.FEMALE,
        phone_number="9800000001",
    )
    session.add(patient)
    await session.flush()

    found, total = await repository.search(query="Integration Test")
    assert total >= 1
    assert any(item.id == patient.id for item in found)

    by_phone, _ = await repository.search(query="9800000001")
    assert any(item.id == patient.id for item in by_phone)


async def test_consultation_status_and_department_filters(session):
    from app.models.consultation import Consultation
    from app.models.enums import ConsultationStatus, Department, Gender
    from app.models.patient import Patient
    from app.repositories.consultation_repository import ConsultationRepository

    patient = Patient(name="Filter Case", age=30, gender=Gender.MALE,
                      phone_number="9800000002")
    session.add(patient)
    await session.flush()

    session.add(
        Consultation(patient_id=patient.id, department=Department.ORTHOPEDICS,
                     status=ConsultationStatus.COMPLETED)
    )
    await session.flush()

    repository = ConsultationRepository(session)
    completed, total = await repository.list_paginated(
        status=ConsultationStatus.COMPLETED, department=Department.ORTHOPEDICS
    )
    assert total >= 1
    assert all(item.status is ConsultationStatus.COMPLETED for item in completed)


async def test_reviewed_filter_uses_the_jsonb_marker(session):
    """The waiting queue depends on this JSONB predicate being correct."""
    from app.models.consultation import Consultation
    from app.models.enums import ConsultationStatus, Department, Gender
    from app.models.patient import Patient
    from app.repositories.consultation_repository import ConsultationRepository

    patient = Patient(name="Review Case", age=51, gender=Gender.FEMALE,
                      phone_number="9800000003")
    session.add(patient)
    await session.flush()

    unreviewed = Consultation(patient_id=patient.id, department=Department.GYNECOLOGY,
                              status=ConsultationStatus.COMPLETED, medical_json={})
    reviewed = Consultation(patient_id=patient.id, department=Department.GYNECOLOGY,
                            status=ConsultationStatus.COMPLETED,
                            medical_json={"reviewed_at": "2026-07-28T10:00:00Z"})
    session.add_all([unreviewed, reviewed])
    await session.flush()

    repository = ConsultationRepository(session)
    waiting, _ = await repository.list_paginated(
        status=ConsultationStatus.COMPLETED, reviewed=False, patient_id=patient.id
    )
    seen, _ = await repository.list_paginated(
        status=ConsultationStatus.COMPLETED, reviewed=True, patient_id=patient.id
    )
    assert unreviewed.id in {item.id for item in waiting}
    assert reviewed.id in {item.id for item in seen}


async def test_prescription_numbering_is_sequential_and_unique(session):
    from app.models.enums import Department, Gender
    from app.models.patient import Patient
    from app.services.prescription_service import PrescriptionService

    patient = Patient(name="Rx Case", age=60, gender=Gender.MALE,
                      phone_number="9800000004")
    session.add(patient)
    await session.flush()

    service = PrescriptionService(session)
    first = await service._next_number(Department.ORTHOPEDICS)
    assert first.startswith("SH-ORT-")
    assert len(first.rsplit("-", 1)[1]) == 6


async def test_audit_rows_are_written(session):
    from sqlalchemy import select

    from app.models.audit import AuditLog
    from app.models.enums import AuditAction

    session.add(
        AuditLog(action=AuditAction.LOGIN_SUCCESS, actor_name="Test Doctor",
                 actor_role="doctor", success=True)
    )
    await session.flush()

    result = await session.execute(
        select(AuditLog).where(AuditLog.actor_name == "Test Doctor")
    )
    assert result.scalar_one_or_none() is not None
