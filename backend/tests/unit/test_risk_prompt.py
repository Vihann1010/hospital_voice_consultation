"""The risk stage builds its prompt at the end of every intake.

It once referred to the hospital name without importing the settings, and
every completed intake lost its summary: the failure only surfaced when the
last stage ran, after the patient had finished talking.
"""
import uuid

import pytest

from app.ai.pipeline.risk_detection import RiskDetectionService
from app.ai.pipeline.schemas import MedicalRecord, RiskAssessment
from app.ai.session.memory import ConversationMemory
from app.core.config import settings
from app.models.enums import Department

pytestmark = pytest.mark.unit


async def test_risk_prompt_names_the_site_and_the_department(monkeypatch):
    seen = {}

    async def fake_run_json(self, *, system, user, ledger, tag):
        seen["system"] = system
        return RiskAssessment.model_validate(
            {"overall_risk": "low", "triage_priority": "routine", "emergency": False,
             "red_flags": [], "recommended_action": "Routine review."}
        )

    monkeypatch.setattr(RiskDetectionService, "run_json", fake_run_json)
    memory = ConversationMemory(
        consultation_id=uuid.uuid4(),
        department=Department.GASTROENTEROLOGY,
        patient_info={"name": "Test", "age": 40, "gender": "male"},
    )
    result = await RiskDetectionService().assess(memory, MedicalRecord())

    assert result.overall_risk == "low"
    assert settings.HOSPITAL_NAME in seen["system"]
    assert "Gastroenterology" in seen["system"]
