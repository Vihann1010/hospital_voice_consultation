"""TPA and insurance claims.

Policies, a claim's progress from pre-authorisation to settlement, the payer's
share put on the bill, and what the payer sent. The rules for each step are in
app/insurance/rules.py; this is where they meet the records.

**The payer's share is a payment on the bill.** Once a claim is approved, the
amount the payer will cover is recorded against the bill as an insurance
payment. The counter then asks the family only for the rest, and the books move
that amount from patients receivable to insurance receivable. If the approval
changes, that payment is struck with a reason, never deleted.

**Settlements clear it.** Money received, TDS the payer deducted and anything
they refused are recorded against the claim, and the books clear insurance
receivable from them. A claim is settled when those add up to the booked
amount. Anything that does not add up is flagged on the claim for a person to
check, not guessed at.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import day_bounds, local_today, to_local
from app.core.financial_year import label_for
from app.insurance import rules
from app.insurance.rules import ClaimRuleError
from app.models.emr import DocumentCounter, InsuranceClaim, InsurancePolicy, Invoice, Payment
from app.models.enums import ClaimStatus, InvoiceStatus, PayerType, PaymentMode
from app.models.insurance import ClaimSettlement
from app.models.ipd import Admission
from app.models.organisation import Organisation
from app.models.patient import Patient

STATUS_ORDER = list(rules.STATUS_LABEL)
# A claim still counts against a stay or bill unless the payer turned it down.
LIVE_STATUSES = [status for status in ClaimStatus
                 if status.value not in (rules.REJECTED, rules.PRE_AUTH_REJECTED)]


class InsuranceError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip() or None


def _rupees(paise: int) -> str:
    return f"Rs {paise / 100:,.2f}"


class InsuranceService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ============================================================ options
    async def options(self) -> Dict[str, Any]:
        payers = (await self.session.execute(
            select(Organisation).where(Organisation.is_active.is_(True)).order_by(Organisation.name)
        )).scalars()
        return {
            "statuses": [{"value": status, "label": rules.STATUS_LABEL[status],
                          "next": [s for s in STATUS_ORDER if s in rules.TRANSITIONS[status]]}
                         for status in STATUS_ORDER],
            "payers": [{"id": org.id, "code": org.code, "name": org.name, "payer_type": org.payer_type.value}
                       for org in payers],
            "payer_types": [p.value for p in PayerType if p is not PayerType.SELF_PAY],
            "settlement_modes": list(rules.SETTLEMENT_MODES),
        }

    # =========================================================== policies
    @staticmethod
    def policy_out(policy: InsurancePolicy, organisation_name: Optional[str] = None) -> Dict[str, Any]:
        return {
            "id": policy.id, "patient_id": policy.patient_id, "payer_type": policy.payer_type.value,
            "insurer_name": policy.insurer_name, "tpa_name": policy.tpa_name,
            "policy_number": policy.policy_number, "member_id": policy.member_id,
            "scheme_name": policy.scheme_name, "valid_from": policy.valid_from, "valid_to": policy.valid_to,
            "sum_insured_paise": policy.sum_insured_paise, "is_active": policy.is_active,
            "organisation_id": policy.organisation_id, "organisation_name": organisation_name,
        }

    async def save_policy(self, data: Dict[str, Any], *, policy_id: Optional[uuid.UUID] = None) -> InsurancePolicy:
        if await self.session.get(Patient, data["patient_id"]) is None:
            raise InsuranceError("Patient not found.", status_code=404)
        if data.get("organisation_id") and await self.session.get(Organisation, data["organisation_id"]) is None:
            raise InsuranceError("That payer is not in the organisation register.")
        if data.get("valid_from") and data.get("valid_to") and data["valid_to"] < data["valid_from"]:
            raise InsuranceError("The policy cannot end before it starts.")
        data = {**data, **{key: _clean(data.get(key)) for key in ("tpa_name", "member_id", "scheme_name")},
                "insurer_name": data["insurer_name"].strip(), "policy_number": data["policy_number"].strip()}
        if not data["insurer_name"] or not data["policy_number"]:
            raise InsuranceError("The insurer and the policy number are needed.")

        if policy_id is not None:
            policy = await self.session.get(InsurancePolicy, policy_id)
            if policy is None:
                raise InsuranceError("Policy not found.", status_code=404)
            if policy.patient_id != data["patient_id"]:
                raise InsuranceError("A policy cannot be moved to another patient.")
        else:
            duplicate = await self.session.scalar(select(InsurancePolicy).where(
                InsurancePolicy.patient_id == data["patient_id"],
                InsurancePolicy.policy_number == data["policy_number"],
                InsurancePolicy.is_active.is_(True),
            ))
            if duplicate is not None:
                raise InsuranceError(f"Policy {data['policy_number']} is already on this patient's record.",
                                     status_code=409)
            policy = InsurancePolicy(patient_id=data["patient_id"], balance_paise=data.get("sum_insured_paise"))
            self.session.add(policy)
        for key in ("organisation_id", "payer_type", "insurer_name", "tpa_name", "policy_number", "member_id",
                    "scheme_name", "valid_from", "valid_to", "sum_insured_paise", "is_active"):
            setattr(policy, key, data.get(key))
        await self.session.flush()
        return policy

    # ======================================================= patient view
    async def patient_context(self, patient_id: uuid.UUID) -> Dict[str, Any]:
        patient = await self.session.get(Patient, patient_id)
        if patient is None:
            raise InsuranceError("Patient not found.", status_code=404)
        policies = list((await self.session.execute(
            select(InsurancePolicy, Organisation)
            .outerjoin(Organisation, Organisation.id == InsurancePolicy.organisation_id)
            .where(InsurancePolicy.patient_id == patient_id)
            .order_by(InsurancePolicy.is_active.desc(), InsurancePolicy.created_at.desc())
        )).all())
        admissions = list((await self.session.execute(
            select(Admission).where(Admission.patient_id == patient_id)
            .order_by(Admission.admitted_at.desc()).limit(10)
        )).scalars())
        bills = list((await self.session.execute(
            select(Invoice).where(Invoice.patient_id == patient_id, Invoice.status != InvoiceStatus.CANCELLED,
                                  Invoice.issued_at.is_not(None))
            .order_by(Invoice.issued_at.desc()).limit(30)
        )).scalars())
        final_bill_of = {admission.final_invoice_id: admission.ip_number
                         for admission in admissions if admission.final_invoice_id}
        return {
            "patient": {"id": patient.id, "name": patient.name, "uhid": patient.uhid},
            "policies": [self.policy_out(policy, org.name if org else None) for policy, org in policies],
            "admissions": [{"id": a.id, "ip_number": a.ip_number, "status": a.status.value,
                            "admitted_at": a.admitted_at, "final_invoice_id": a.final_invoice_id}
                           for a in admissions],
            "bills": [{"id": b.id, "invoice_number": b.invoice_number, "issued_at": b.issued_at,
                       "status": b.status.value, "total_paise": b.total_paise, "paid_paise": b.paid_paise,
                       "balance_paise": b.balance_paise, "admission_ip_number": final_bill_of.get(b.id)}
                      for b in bills],
            "claims": await self.claims(patient_id=patient_id, limit=50),
        }

    # ============================================================ claims
    async def _next_number(self, on: date) -> str:
        year = label_for(on)
        scope = "insurance-claim"
        lookup = (select(DocumentCounter)
                  .where(DocumentCounter.scope == scope, DocumentCounter.period == year).with_for_update())
        counter = (await self.session.execute(lookup)).scalar_one_or_none()
        if counter is None:
            try:
                async with self.session.begin_nested():
                    counter = DocumentCounter(scope=scope, period=year, last_value=0)
                    self.session.add(counter)
                    await self.session.flush()
            except IntegrityError:
                counter = (await self.session.execute(lookup)).scalar_one()
        counter.last_value += 1
        await self.session.flush()
        return f"CLM/{year}/{counter.last_value:05d}"

    @staticmethod
    def _history(claim: InsuranceClaim, by: str, note: Optional[str] = None, **extra: Any) -> None:
        entry = {"at": _now().isoformat(), "status": claim.status.value, "by": by}
        if note:
            entry["note"] = note
        entry.update({key: value for key, value in extra.items() if value is not None})
        claim.history = list(claim.history or []) + [entry]

    async def _lock(self, claim_id: uuid.UUID) -> InsuranceClaim:
        claim = await self.session.scalar(
            select(InsuranceClaim).where(InsuranceClaim.id == claim_id).with_for_update()
        )
        if claim is None:
            raise InsuranceError("Claim not found.", status_code=404)
        return claim

    async def _settlements(self, claim_ids: Sequence[uuid.UUID]) -> Dict[uuid.UUID, List[ClaimSettlement]]:
        found: Dict[uuid.UUID, List[ClaimSettlement]] = {claim_id: [] for claim_id in claim_ids}
        if claim_ids:
            for settlement in (await self.session.execute(
                select(ClaimSettlement).where(ClaimSettlement.claim_id.in_(list(claim_ids)))
                .order_by(ClaimSettlement.received_on, ClaimSettlement.created_at)
            )).scalars():
                found[settlement.claim_id].append(settlement)
        return found

    async def _sync_booking(self, claim: InsuranceClaim) -> None:
        """Notice a bill entry struck at the counter instead of through the claim."""
        if claim.booking_payment_id is None:
            return
        payment = await self.session.get(Payment, claim.booking_payment_id)
        if payment is not None and payment.cancelled_at is None:
            return
        claim.booked_paise = 0
        claim.booking_payment_id = None
        self._history(claim, "System", "The claim's entry on the bill was struck at the counter, so nothing is "
                                       "booked to the bill now.")
        await self.session.flush()

    async def create_claim(self, data: Dict[str, Any], *, by: str) -> InsuranceClaim:
        policy = await self.session.get(InsurancePolicy, data["policy_id"])
        if policy is None:
            raise InsuranceError("Policy not found.", status_code=404)
        if not policy.is_active:
            raise InsuranceError("This policy is marked as no longer in use.")

        admission: Optional[Admission] = None
        invoice: Optional[Invoice] = None
        if data.get("admission_id"):
            admission = await self.session.get(Admission, data["admission_id"])
            if admission is None:
                raise InsuranceError("Admission not found.", status_code=404)
            if admission.patient_id != policy.patient_id:
                raise InsuranceError("That admission is another patient's.")
        if data.get("invoice_id"):
            invoice = await self.session.get(Invoice, data["invoice_id"])
            if invoice is None:
                raise InsuranceError("Bill not found.", status_code=404)
            if invoice.patient_id != policy.patient_id:
                raise InsuranceError("That bill is another patient's.")
            if invoice.status is InvoiceStatus.CANCELLED:
                raise InsuranceError("That bill has been cancelled.")
        if admission is not None and invoice is None and admission.final_invoice_id:
            invoice = await self.session.get(Invoice, admission.final_invoice_id)
        if admission is None and invoice is not None:
            admission = await self.session.scalar(select(Admission).where(Admission.final_invoice_id == invoice.id))
        if admission is not None and invoice is not None and admission.final_invoice_id not in (None, invoice.id):
            raise InsuranceError("That bill is not this admission's final bill.")

        if admission is not None:
            treated_on = to_local(admission.admitted_at).date()
        elif invoice is not None and invoice.issued_at is not None:
            treated_on = to_local(invoice.issued_at).date()
        else:
            treated_on = local_today()
        if (policy.valid_from and treated_on < policy.valid_from) or (policy.valid_to and treated_on > policy.valid_to):
            cover = f"{policy.valid_from:%d %b %Y}" if policy.valid_from else "its start"
            cover_to = f"{policy.valid_to:%d %b %Y}" if policy.valid_to else "no end date"
            raise InsuranceError(f"The policy covers {cover} to {cover_to}; the treatment on "
                                 f"{treated_on:%d %b %Y} falls outside it.")

        conditions = []
        if admission is not None:
            conditions.append(InsuranceClaim.admission_id == admission.id)
        if invoice is not None:
            conditions.append(InsuranceClaim.invoice_id == invoice.id)
        if conditions:
            existing = await self.session.scalar(select(InsuranceClaim).where(
                or_(*conditions), InsuranceClaim.policy_id == policy.id, InsuranceClaim.status.in_(LIVE_STATUSES),
            ))
            if existing is not None:
                raise InsuranceError(
                    f"Claim {existing.claim_number} is already open for this "
                    f"{'admission' if admission is not None else 'bill'} on this policy.", status_code=409)

        organisation = await self.session.get(Organisation, policy.organisation_id) if policy.organisation_id else None
        claim = InsuranceClaim(
            claim_number=await self._next_number(local_today()),
            policy_id=policy.id, patient_id=policy.patient_id,
            admission_id=admission.id if admission else None, invoice_id=invoice.id if invoice else None,
            visit_id=(invoice.visit_id if invoice else None) or (admission.visit_id if admission else None),
            organisation_id=policy.organisation_id,
            payer_name=organisation.name if organisation else (policy.tpa_name or policy.insurer_name),
            status=ClaimStatus.DRAFT, diagnosis=_clean(data.get("diagnosis")),
            treatment_summary=_clean(data.get("treatment_summary")),
            external_reference=_clean(data.get("external_reference")), created_by_name=by, history=[],
        )
        self._history(claim, by, "Claim opened")
        self.session.add(claim)
        await self.session.flush()
        return claim

    AMOUNTS = {"pre_auth_requested_paise": "pre_auth_requested", "pre_auth_approved_paise": "pre_auth_approved",
               "claimed_paise": "claimed", "approved_paise": "approved"}

    async def move(self, claim_id: uuid.UUID, data: Dict[str, Any], *, by: str) -> Tuple[InsuranceClaim, str]:
        claim = await self._lock(claim_id)
        await self._sync_booking(claim)
        target = data["status"]
        figures = {name: (data[field] if data.get(field) is not None else getattr(claim, field))
                   for field, name in self.AMOUNTS.items()}
        figures["booked"] = claim.booked_paise
        try:
            rules.check_move(claim.status.value, target, figures, reason=data.get("reason"), query=data.get("query"))
        except ClaimRuleError as exc:
            raise InsuranceError(str(exc)) from exc

        changed = {}
        for field in list(self.AMOUNTS) + ["patient_liability_paise"]:
            if data.get(field) is not None and data[field] != getattr(claim, field):
                changed[field] = data[field]
                setattr(claim, field, data[field])
        if data.get("external_reference") is not None:
            claim.external_reference = _clean(data["external_reference"])
        now = _now()
        if target == rules.SUBMITTED and claim.submitted_at is None:
            claim.submitted_at = now
        if target in (rules.APPROVED, rules.PARTIALLY_APPROVED, rules.REJECTED):
            claim.decided_at = now
        if target in (rules.REJECTED, rules.PRE_AUTH_REJECTED):
            claim.rejection_reason = data["reason"].strip()
        if target == rules.QUERIED:
            claim.query_detail = data["query"].strip()
        previous = claim.status.value
        claim.status = ClaimStatus(target)
        note = _clean(data.get("note")) or _clean(data.get("reason")) or _clean(data.get("query"))
        self._history(claim, by, note, **changed)
        await self.session.flush()
        return claim, previous

    async def book(self, claim_id: uuid.UUID, amount: int, *, by: str,
                   user_id: Optional[uuid.UUID]) -> Tuple[InsuranceClaim, Payment]:
        from app.services.reception_service import ReceptionError, ReceptionService

        claim = await self._lock(claim_id)
        await self._sync_booking(claim)
        invoice_id = claim.invoice_id
        if invoice_id is None and claim.admission_id is not None:
            admission = await self.session.get(Admission, claim.admission_id)
            invoice_id = admission.final_invoice_id if admission else None
        if invoice_id is None:
            raise InsuranceError("Raise the final bill first, then put the approved amount on it.")
        invoice = await self.session.scalar(select(Invoice).where(Invoice.id == invoice_id).with_for_update())
        if invoice is None or invoice.status is InvoiceStatus.CANCELLED:
            raise InsuranceError("That bill has been cancelled.")
        try:
            rules.check_booking(status=claim.status.value, approved=claim.approved_paise, booked=claim.booked_paise,
                                amount=amount, bill_balance=invoice.balance_paise)
        except ClaimRuleError as exc:
            raise InsuranceError(str(exc)) from exc
        try:
            payment = await ReceptionService(self.session).record_payment(
                invoice_id=invoice.id, amount_paise=amount, mode=PaymentMode.INSURANCE,
                reference=claim.claim_number,
                mode_details={"payer_name": (claim.payer_name or "Insurer")[:120],
                              "claim_reference": (claim.external_reference or claim.claim_number)[:64]},
                received_by_id=user_id, received_by_name=by,
            )
        except ReceptionError as exc:
            raise InsuranceError(str(exc)) from exc
        policy = await self.session.get(InsurancePolicy, claim.policy_id)
        invoice.payer_type = policy.payer_type if policy else PayerType.INSURANCE
        invoice.payer_covered_paise = amount
        claim.invoice_id = invoice.id
        claim.booked_paise = amount
        claim.booking_payment_id = payment.id
        self._history(claim, by, f"{_rupees(amount)} put on bill {invoice.invoice_number} as the payer's share "
                                 f"(receipt {payment.receipt_number})")
        await self.session.flush()
        return claim, payment

    async def unbook(self, claim_id: uuid.UUID, reason: str, *, by: str) -> InsuranceClaim:
        from app.services.reception_service import ReceptionError, ReceptionService

        if not (reason or "").strip():
            raise InsuranceError("Taking the payer's share off the bill needs a reason.")
        claim = await self._lock(claim_id)
        await self._sync_booking(claim)
        if not claim.booked_paise or claim.booking_payment_id is None:
            raise InsuranceError("Nothing from this claim is on the bill.")
        settlements = (await self._settlements([claim.id]))[claim.id]
        if any(s.cancelled_at is None for s in settlements):
            raise InsuranceError("The payer's payments are recorded against this claim. Cancel those first.")
        try:
            payment = await ReceptionService(self.session).cancel_receipt(
                claim.booking_payment_id, reason=f"Claim {claim.claim_number} taken off the bill: {reason.strip()}",
                cancelled_by_name=by,
            )
        except ReceptionError as exc:
            raise InsuranceError(str(exc)) from exc
        invoice = await self.session.get(Invoice, payment.invoice_id)
        if invoice is not None:
            invoice.payer_covered_paise = 0
        amount = claim.booked_paise
        claim.booked_paise = 0
        claim.booking_payment_id = None
        self._history(claim, by, f"{_rupees(amount)} taken off the bill: {reason.strip()}")
        await self.session.flush()
        return claim

    # ======================================================= settlements
    def _recount(self, claim: InsuranceClaim, settlements: List[ClaimSettlement], by: str) -> None:
        live = [s for s in settlements if s.cancelled_at is None]
        claim.settled_paise = sum(s.received_paise + s.tds_paise for s in live)
        accounted = sum(s.received_paise + s.tds_paise + s.deduction_paise for s in live)
        if claim.booked_paise and accounted >= claim.booked_paise and claim.status is not ClaimStatus.SETTLED:
            claim.status = ClaimStatus.SETTLED
            claim.settled_at = _now()
            self._history(claim, by, "Settled: the payer's payments account for the whole amount on the bill.")
        elif claim.status is ClaimStatus.SETTLED and accounted < claim.booked_paise:
            claim.status = (ClaimStatus.APPROVED if claim.approved_paise >= claim.claimed_paise
                            else ClaimStatus.PARTIALLY_APPROVED)
            claim.settled_at = None
            self._history(claim, by, "Reopened: a settlement was cancelled, so the payer still owes part of it.")

    async def settle(self, claim_id: uuid.UUID, data: Dict[str, Any], *, by: str) -> Tuple[InsuranceClaim,
                                                                                            ClaimSettlement]:
        claim = await self._lock(claim_id)
        await self._sync_booking(claim)
        if data["received_on"] > local_today():
            raise InsuranceError("The date the payer paid cannot be in the future.")
        settlements = (await self._settlements([claim.id]))[claim.id]
        already = sum(s.received_paise + s.tds_paise + s.deduction_paise
                      for s in settlements if s.cancelled_at is None)
        received, tds, deduction = (int(data.get(key) or 0)
                                    for key in ("received_paise", "tds_paise", "deduction_paise"))
        try:
            rules.check_settlement(booked=claim.booked_paise, already_settled=already, received=received, tds=tds,
                                   deduction=deduction, deduction_reason=data.get("deduction_reason"),
                                   mode=data["mode"])
        except ClaimRuleError as exc:
            raise InsuranceError(str(exc)) from exc
        if received and not _clean(data.get("reference")):
            raise InsuranceError("Enter the bank transfer (UTR), cheque or UPI reference for the money received.")
        settlement = ClaimSettlement(
            claim_id=claim.id, received_on=data["received_on"], received_paise=received, tds_paise=tds,
            deduction_paise=deduction, deduction_reason=_clean(data.get("deduction_reason")), mode=data["mode"],
            reference=_clean(data.get("reference")), notes=_clean(data.get("notes")), created_by_name=by,
        )
        self.session.add(settlement)
        await self.session.flush()
        parts = [f"{_rupees(received)} received" if received else None, f"TDS {_rupees(tds)}" if tds else None,
                 f"{_rupees(deduction)} disallowed" if deduction else None]
        self._history(claim, by, "Payer settlement recorded: " + ", ".join(p for p in parts if p))
        self._recount(claim, settlements + [settlement], by)
        await self.session.flush()
        return claim, settlement

    async def cancel_settlement(self, settlement_id: uuid.UUID, reason: str, *, by: str) -> Tuple[InsuranceClaim,
                                                                                                   ClaimSettlement]:
        if not (reason or "").strip():
            raise InsuranceError("Cancelling a settlement needs a reason.")
        settlement = await self.session.scalar(
            select(ClaimSettlement).where(ClaimSettlement.id == settlement_id).with_for_update()
        )
        if settlement is None:
            raise InsuranceError("Settlement not found.", status_code=404)
        claim = await self._lock(settlement.claim_id)
        if settlement.cancelled_at is not None:
            raise InsuranceError("This settlement has already been cancelled.")
        settlement.cancelled_at = _now()
        settlement.cancelled_by_name = by
        settlement.cancel_reason = reason.strip()
        await self.session.flush()
        total = settlement.received_paise + settlement.tds_paise + settlement.deduction_paise
        self._history(claim, by, f"Settlement of {_rupees(total)} cancelled: {reason.strip()}")
        self._recount(claim, (await self._settlements([claim.id]))[claim.id], by)
        await self.session.flush()
        return claim, settlement

    # ============================================================ reading
    @staticmethod
    def settlement_out(s: ClaimSettlement) -> Dict[str, Any]:
        return {"id": s.id, "received_on": s.received_on, "received_paise": s.received_paise,
                "tds_paise": s.tds_paise, "deduction_paise": s.deduction_paise,
                "deduction_reason": s.deduction_reason, "mode": s.mode, "reference": s.reference,
                "notes": s.notes, "created_by_name": s.created_by_name, "created_at": s.created_at,
                "cancelled_at": s.cancelled_at, "cancelled_by_name": s.cancelled_by_name,
                "cancel_reason": s.cancel_reason}

    def _out(self, claim: InsuranceClaim, patient: Patient, policy: InsurancePolicy, invoice: Optional[Invoice],
             admission: Optional[Admission], settlements: List[ClaimSettlement], booking: Optional[Payment],
             *, detail: bool = False) -> Dict[str, Any]:
        live = [s for s in settlements if s.cancelled_at is None]
        received = sum(s.received_paise for s in live)
        tds = sum(s.tds_paise for s in live)
        deducted = sum(s.deduction_paise for s in live)
        accounted = received + tds + deducted
        booked = claim.booked_paise
        attention: List[str] = []
        if accounted > booked:
            attention.append(f"The payer's recorded payments come to {_rupees(accounted)}, more than the "
                             f"{_rupees(booked)} on the bill. Unclear: please check this claim manually.")
        if booked and booking is not None and booking.cancelled_at is not None:
            attention.append("The bill entry for this claim was struck. Unclear: please check this claim manually.")
        started = claim.submitted_at or claim.created_at
        status = claim.status.value
        out = {
            "id": claim.id, "claim_number": claim.claim_number, "status": status,
            "status_label": rules.STATUS_LABEL[status],
            "next_statuses": [s for s in STATUS_ORDER if s in rules.TRANSITIONS[status]],
            "patient": {"id": patient.id, "name": patient.name, "uhid": patient.uhid},
            "policy": self.policy_out(policy),
            "payer_name": claim.payer_name, "organisation_id": claim.organisation_id,
            "admission": ({"id": admission.id, "ip_number": admission.ip_number, "status": admission.status.value}
                          if admission else None),
            "invoice": ({"id": invoice.id, "invoice_number": invoice.invoice_number, "status": invoice.status.value,
                         "total_paise": invoice.total_paise, "paid_paise": invoice.paid_paise,
                         "balance_paise": invoice.balance_paise} if invoice else None),
            "external_reference": claim.external_reference,
            "pre_auth_requested_paise": claim.pre_auth_requested_paise,
            "pre_auth_approved_paise": claim.pre_auth_approved_paise,
            "claimed_paise": claim.claimed_paise, "approved_paise": claim.approved_paise,
            "booked_paise": booked,
            "booked_on": to_local(booking.received_at).date() if booking is not None and booked else None,
            "booking_receipt_number": booking.receipt_number if booking is not None and booked else None,
            "received_paise": received, "tds_paise": tds, "deducted_paise": deducted,
            "outstanding_paise": max(booked - accounted, 0),
            "patient_liability_paise": claim.patient_liability_paise,
            "diagnosis": claim.diagnosis, "treatment_summary": claim.treatment_summary,
            "rejection_reason": claim.rejection_reason, "query_detail": claim.query_detail,
            "submitted_at": claim.submitted_at, "decided_at": claim.decided_at, "settled_at": claim.settled_at,
            "created_at": claim.created_at, "created_by_name": claim.created_by_name,
            "age_days": (local_today() - to_local(started).date()).days,
            "can_book": status in rules.BOOKABLE and not booked,
            "attention": attention,
        }
        if detail:
            out["history"] = list(reversed(claim.history or []))
            out["settlements"] = [self.settlement_out(s) for s in settlements]
        return out

    async def _rows(self, statement) -> List[Dict[str, Any]]:
        rows = (await self.session.execute(statement)).all()
        settlements = await self._settlements([row[0].id for row in rows])
        booking_ids = [row[0].booking_payment_id for row in rows if row[0].booking_payment_id]
        bookings = {}
        if booking_ids:
            bookings = {p.id: p for p in (await self.session.execute(
                select(Payment).where(Payment.id.in_(booking_ids)))).scalars()}
        return [(row, settlements[row[0].id], bookings.get(row[0].booking_payment_id)) for row in rows]

    def _base(self):
        return (select(InsuranceClaim, Patient, InsurancePolicy, Invoice, Admission)
                .join(Patient, Patient.id == InsuranceClaim.patient_id)
                .join(InsurancePolicy, InsurancePolicy.id == InsuranceClaim.policy_id)
                .outerjoin(Invoice, Invoice.id == InsuranceClaim.invoice_id)
                .outerjoin(Admission, Admission.id == InsuranceClaim.admission_id))

    async def claims(
        self, *, status: Optional[str] = None, organisation_id: Optional[uuid.UUID] = None,
        patient_id: Optional[uuid.UUID] = None, q: Optional[str] = None,
        created_from: Optional[date] = None, created_to: Optional[date] = None, limit: int = 200,
    ) -> List[Dict[str, Any]]:
        statement = self._base()
        if status == "open":
            statement = statement.where(InsuranceClaim.status.in_([ClaimStatus(s) for s in rules.OPEN]))
        elif status:
            try:
                statement = statement.where(InsuranceClaim.status == ClaimStatus(status))
            except ValueError as exc:
                raise InsuranceError(f"{status} is not a claim status.") from exc
        if organisation_id is not None:
            statement = statement.where(InsuranceClaim.organisation_id == organisation_id)
        if patient_id is not None:
            statement = statement.where(InsuranceClaim.patient_id == patient_id)
        if q and q.strip():
            like = f"%{q.strip()}%"
            statement = statement.where(or_(
                InsuranceClaim.claim_number.ilike(like), Patient.name.ilike(like), Patient.uhid.ilike(like),
                InsuranceClaim.external_reference.ilike(like), InsurancePolicy.policy_number.ilike(like),
                Admission.ip_number.ilike(like), InsuranceClaim.payer_name.ilike(like),
            ))
        if created_from is not None:
            statement = statement.where(InsuranceClaim.created_at >= day_bounds(created_from)[0])
        if created_to is not None:
            statement = statement.where(InsuranceClaim.created_at < day_bounds(created_to)[1])
        statement = statement.order_by(InsuranceClaim.created_at.desc()).limit(limit)
        return [self._out(*row, settlements, booking) for row, settlements, booking in await self._rows(statement)]

    async def claim(self, claim_id: uuid.UUID) -> Dict[str, Any]:
        claim = await self.session.get(InsuranceClaim, claim_id)
        if claim is None:
            raise InsuranceError("Claim not found.", status_code=404)
        await self._sync_booking(claim)
        found = await self._rows(self._base().where(InsuranceClaim.id == claim_id))
        row, settlements, booking = found[0]
        return self._out(*row, settlements, booking, detail=True)

    async def outstanding(self, as_of: date) -> Dict[str, Any]:
        """What payers still owe on claims booked to bills by `as_of`, with age."""
        rows = (await self.session.execute(
            select(InsuranceClaim, Patient, Payment)
            .join(Patient, Patient.id == InsuranceClaim.patient_id)
            .join(Payment, Payment.id == InsuranceClaim.booking_payment_id)
            .where(InsuranceClaim.booked_paise > 0, Payment.cancelled_at.is_(None))
        )).all()
        settlements = await self._settlements([claim.id for claim, _, _ in rows])
        items, payers = [], {}
        for claim, patient, payment in rows:
            booked_on = to_local(payment.received_at).date()
            if booked_on > as_of:
                continue
            settled = sum(s.received_paise + s.tds_paise + s.deduction_paise for s in settlements[claim.id]
                          if s.cancelled_at is None and s.received_on <= as_of)
            owed = claim.booked_paise - settled
            if owed <= 0:
                continue
            age = (as_of - booked_on).days
            bucket = rules.ageing_bucket(age)
            items.append({
                "claim_id": claim.id, "claim_number": claim.claim_number, "payer_name": claim.payer_name,
                "patient_name": patient.name, "uhid": patient.uhid or "", "status": claim.status.value,
                "external_reference": claim.external_reference or "", "booked_on": booked_on, "age_days": age,
                "bucket": bucket, "booked_paise": claim.booked_paise, "settled_paise": settled,
                "outstanding_paise": owed,
            })
            payer = payers.setdefault(claim.payer_name or "Not named", {
                "payer_name": claim.payer_name or "Not named", "claims": 0, "outstanding_paise": 0,
                **{b: 0 for b in rules.AGEING_BUCKETS},
            })
            payer["claims"] += 1
            payer["outstanding_paise"] += owed
            payer[bucket] += owed
        items.sort(key=lambda item: (-item["age_days"], item["claim_number"]))
        return {"as_of": as_of, "buckets": list(rules.AGEING_BUCKETS), "items": items,
                "payers": sorted(payers.values(), key=lambda p: -p["outstanding_paise"]),
                "total_paise": sum(item["outstanding_paise"] for item in items)}
