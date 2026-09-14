"""What a patient is actually charged, and why.

The counter should not have to remember that Dr Agarwal sees a patient again
free within seven days, or that this employer pays four hundred rupees for a
consultation rather than five. Those rules were captured in the consultant
register and the organisation master; until now nothing read them, so they
were decoration. This applies them.

**Every decision carries its reason.** A line that comes out at zero prints
"Free follow-up — seen 4 Sept, within 7 days" rather than a silent zero.
A patient who is not charged wants to know why, an auditor wants to know why,
and a clerk who sees an unexpected zero needs to be able to tell the
difference between a rule and a bug.

**Rules are applied in a fixed order, and the first that hits wins.**
Negotiated rate, then free follow-up, then first-consultation-free. They are
not combined: applying a free-follow-up to a negotiated rate is still free,
and stacking a discount on a waiver is how a bill goes negative.

**Nothing here overrides an explicit price.** If the caller states a rate, it
is used and marked as an override. Reception sometimes has to charge what the
doctor said to charge, and a system that silently refuses is a system staff
work around on paper.
"""
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import local_today, to_local
from app.models.consultant import Consultant
from app.models.emr import Invoice, InvoiceLine, ServiceItem
from app.models.enums import InvoiceStatus, ServiceCategory
from app.models.organisation import NegotiatedRate, Organisation


@dataclass(frozen=True)
class PriceDecision:
    """What one line costs, and the rule that decided it."""

    rate_paise: int
    #: Machine-readable, for reports: tariff | negotiated | org_discount |
    #: free_follow_up | first_free | override
    rule: str
    #: One sentence for the bill and the screen. Empty for a plain tariff
    #: rate, which needs no explanation.
    note: str = ""

    @property
    def is_free(self) -> bool:
        return self.rate_paise == 0


@dataclass
class PricingContext:
    """Everything the rules need, resolved once for a whole bill."""

    patient_id: Optional[uuid.UUID] = None
    consultant: Optional[Consultant] = None
    organisation: Optional[Organisation] = None
    #: service_item_id -> negotiated rate in paise
    negotiated: Dict[uuid.UUID, int] = None  # type: ignore[assignment]
    #: The consultant's own last consultation with this patient, if any.
    last_consultation_on: Optional[Any] = None
    had_any_consultation: bool = False

    def __post_init__(self) -> None:
        if self.negotiated is None:
            self.negotiated = {}


async def build_context(
    session: AsyncSession,
    *,
    patient_id: Optional[uuid.UUID],
    consultant_id: Optional[uuid.UUID] = None,
    doctor_name: Optional[str] = None,
    organisation_id: Optional[uuid.UUID] = None,
) -> PricingContext:
    """Resolve the pricing context for a bill in a handful of queries.

    Built once per invoice rather than per line: a ten-line bill would
    otherwise ask the same three questions ten times.
    """
    context = PricingContext(patient_id=patient_id)

    consultant: Optional[Consultant] = None
    if consultant_id is not None:
        consultant = await session.get(Consultant, consultant_id)
    elif doctor_name:
        # The counter identifies a doctor by name today; the register is
        # matched on it so the rules still apply until every screen passes
        # an id.
        consultant = await session.scalar(
            select(Consultant).where(
                Consultant.full_name == doctor_name, Consultant.is_active.is_(True)
            )
        )
    context.consultant = consultant

    if organisation_id is not None:
        organisation = await session.get(Organisation, organisation_id)
        if organisation is not None and organisation.is_active:
            context.organisation = organisation
            result = await session.execute(
                select(NegotiatedRate.service_item_id, NegotiatedRate.rate_paise)
                .where(NegotiatedRate.organisation_id == organisation.id)
            )
            context.negotiated = {
                service_id: rate for service_id, rate in result.all()
            }

    # When did this consultant last bill this patient for a consultation,
    # and have they ever? Both answers come from one query.
    #
    # Asked of the invoice rather than the visit. A bill raised at the
    # counter need not have a visit attached, and reaching through one would
    # make these rules fire for some patients and not others depending on
    # how the bill happened to be raised.
    if patient_id is not None and consultant is not None:
        result = await session.execute(
            select(Invoice.issued_at, Invoice.created_at)
            .join(InvoiceLine, InvoiceLine.invoice_id == Invoice.id)
            .join(ServiceItem, ServiceItem.id == InvoiceLine.service_item_id)
            .where(
                Invoice.patient_id == patient_id,
                Invoice.doctor_name == consultant.full_name,
                ServiceItem.category == ServiceCategory.CONSULTATION,
                # A cancelled bill is not an attendance. Counting it would
                # give a free follow-up for a visit that was undone.
                Invoice.status != InvoiceStatus.CANCELLED,
            )
            .order_by(Invoice.created_at.desc())
            .limit(1)
        )
        row = result.first()
        if row is not None:
            issued_at, created_at = row
            context.last_consultation_on = to_local(issued_at or created_at).date()
            context.had_any_consultation = True

    return context


def _is_consultation(service: Optional[ServiceItem], context: PricingContext) -> bool:
    """Is this line the consultant's own consultation fee?

    Checked by the consultant's configured service code where one is set, and
    by category otherwise. Without this, a free follow-up would zero the
    X-ray as well.
    """
    if service is None:
        return False
    if context.consultant and context.consultant.consultation_service_code:
        return service.code == context.consultant.consultation_service_code
    return service.category is ServiceCategory.CONSULTATION


def decide(
    *,
    service: Optional[ServiceItem],
    context: PricingContext,
    explicit_rate_paise: Optional[int] = None,
) -> PriceDecision:
    """Price one line."""
    if explicit_rate_paise is not None:
        return PriceDecision(
            rate_paise=int(explicit_rate_paise),
            rule="override",
            note="Price set at the counter",
        )

    if service is None:
        raise ValueError("A line with no service needs an explicit rate.")

    base = service.rate_paise
    rule = "tariff"
    note = ""

    if context.organisation is not None:
        negotiated = context.negotiated.get(service.id)
        if negotiated is not None:
            base = negotiated
            rule = "negotiated"
            note = f"{context.organisation.name} agreed rate"
        elif context.organisation.default_discount_percent:
            percent = context.organisation.default_discount_percent
            # Rounded down to the paisa in the patient's favour. Rounding up
            # means the hospital charges a rupee more than the agreement says
            # on exactly the lines nobody checks.
            base = base - (base * percent) // 100
            rule = "org_discount"
            note = f"{context.organisation.name} {percent}% agreed discount"

    consultant = context.consultant
    if consultant is not None and _is_consultation(service, context):
        if (
            consultant.free_follow_up_days > 0
            and context.last_consultation_on is not None
        ):
            window = timedelta(days=consultant.free_follow_up_days)
            seen_on = context.last_consultation_on
            if local_today() - seen_on <= window:
                return PriceDecision(
                    rate_paise=0,
                    rule="free_follow_up",
                    note=(
                        f"Free follow-up — seen {seen_on:%d %b}, within "
                        f"{consultant.free_follow_up_days} days"
                    ),
                )
        if consultant.first_consultation_free and not context.had_any_consultation:
            return PriceDecision(
                rate_paise=0,
                rule="first_free",
                note=f"First consultation with {consultant.full_name} is free",
            )

    return PriceDecision(rate_paise=base, rule=rule, note=note)


def explain(decisions: List[PriceDecision]) -> List[str]:
    """The notes worth showing, in order, with duplicates removed."""
    seen: List[str] = []
    for decision in decisions:
        if decision.note and decision.note not in seen:
            seen.append(decision.note)
    return seen
