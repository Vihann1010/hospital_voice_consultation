"""Narrative summarisation of an uploaded investigation report.

The division of labour matters: `app/investigations/parsing.py` has already
decided, arithmetically, which values are outside their reference range. This
service receives that verdict and writes the clinical narrative around it. It
is explicitly instructed not to re-classify values, so a model that misreads a
number cannot flip a normal result to abnormal or the reverse.
"""
import json
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.ai.pipeline.base_service import BaseAIService
from app.ai.pipeline.schemas import ReportSummary
from app.ai.providers.base import CostLedger


class ReportSummaryService(BaseAIService[ReportSummary]):
    stage = "report_summary"
    tier = "dialogue"     # the doctor reads this directly; quality matters
    temperature = 0.15
    max_tokens = 1300
    output_model = ReportSummary

    async def summarize(
        self,
        *,
        patient: Dict[str, Any],
        department: str,
        analysis: Dict[str, Any],
        raw_text_excerpt: str,
        previous_summary: Optional[Dict[str, Any]] = None,
        ledger: Optional[CostLedger] = None,
        tag: str = "-",
    ) -> ReportSummary:
        system = (
            f"You summarise laboratory and imaging reports for a specialist at "
            f"{settings.HOSPITAL_NAME}"
            f"Hospital ({department}). Audience: the treating doctor.\n\n"
            "CRITICAL RULE: the abnormal/normal classification of every numeric value has "
            "ALREADY been decided arithmetically against reference ranges and is given to "
            "you in `deterministic_analysis`. Do NOT re-classify any value, do NOT contradict "
            "a flag, and do NOT invent values that are not in the data. If a value is marked "
            "`unknown` because units could not be reconciled, say so plainly rather than "
            "guessing.\n\n"
            "Write `headline` as one sentence a doctor can read in three seconds. "
            "`doctor_summary` is a short paragraph tying the abnormal results together into "
            "a clinical picture. `key_findings` covers only what changes management — a mildly "
            "off value with no consequence is `incidental` or omitted. `patterns_noticed` is "
            "for combinations that matter (for example low haemoglobin with low MCV suggesting "
            "iron deficiency). If narrative text from a radiologist or pathologist is present, "
            "carry its conclusion faithfully. Never state a diagnosis as established, and never "
            "recommend a specific drug or dose."
        )
        payload = {
            "patient": patient,
            "deterministic_analysis": analysis,
            "report_text_excerpt": raw_text_excerpt[:6000],
        }
        if previous_summary:
            payload["previous_version_summary"] = previous_summary
            system += (
                "\n\nA previous version of this same report exists. Use "
                "`comparison_with_previous` to state plainly what changed between versions."
            )
        return await self.run_json(
            system=system,
            user=json.dumps(payload, ensure_ascii=False, default=str),
            ledger=ledger,
            tag=tag,
        )
