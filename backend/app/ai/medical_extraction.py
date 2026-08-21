"""Turns a running transcript into the structured Medical JSON."""
import json
import re
from typing import Any, Dict, Optional

from app.ai.llm_client import llm_client
from app.ai.prompts import MEDICAL_EXTRACTION_SYSTEM, build_extraction_user_prompt
from app.core.logging import get_logger
from app.models.enums import Department

logger = get_logger(__name__)

EMPTY_MEDICAL_JSON: Dict[str, Any] = {
    "chief_complaint": None,
    "symptoms": [],
    "pain": {
        "location": None,
        "character": None,
        "score_out_of_10": None,
        "aggravating_factors": None,
        "relieving_factors": None,
    },
    "duration": None,
    "medical_history": [],
    "current_medicines": [],
    "previous_surgeries": [],
    "allergies": [],
    "weight_kg": None,
    "height_cm": None,
    "department_specific": {},
    "red_flags": [],
    "summary_for_doctor": None,
}

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.DOTALL).strip()
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if match:
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None
    return None


async def extract_medical_json(department: Department, transcript: str) -> Optional[Dict[str, Any]]:
    """One LLM call over the full transcript; None on failure so callers keep the previous version."""
    if not transcript.strip():
        return dict(EMPTY_MEDICAL_JSON)
    try:
        raw = await llm_client.complete_chat(
            [
                {"role": "system", "content": MEDICAL_EXTRACTION_SYSTEM},
                {"role": "user", "content": build_extraction_user_prompt(department, transcript)},
            ],
            temperature=0.1,
        )
    except Exception:
        logger.exception("medical_extraction_llm_failed")
        return None
    parsed = _parse_json(raw)
    if parsed is None:
        logger.error("medical_extraction_parse_failed", extra={"raw_head": raw[:200]})
        return None
    # Guarantee every top-level key exists so downstream consumers can rely on the shape.
    merged = {**EMPTY_MEDICAL_JSON, **parsed}
    return merged
