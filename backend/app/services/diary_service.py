"""The patient diary: one patient's whole financial history, in one place.

This is the screen staff open to answer "what does this patient owe", which
at a counter is asked more often than anything except "what is the next
token". Before this it could only be answered by opening the OPD list, the
ward, and the wallet in three tabs and adding up by hand.

Three decisions shape it.

**Every entry is the same shape.** An OPD bill, an inpatient stay and a
wallet movement are different things clinically and identical financially:
each has a date, a gross, a discount, a net, what was received, what was
returned, and what it leaves owing. Rendering them as one column set is what
makes the running balance readable at all.

**The running balance is computed forward from the oldest entry.** Not
stored, because it is a view of other tables and a stored copy would drift;
and computed oldest-first even though the screen shows newest-first, because
a balance that runs the wrong way round is not a balance.

**Cancelled bills are shown and excluded.** They are kept visible — a patient
asking about a bill they were handed needs to find it — but contribute
nothing to any total. Hiding them makes the diary disagree with the paper the
patient is holding; counting them makes it disagree with the ledger.
"""
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import to_local
from app.models.emr import Invoice, PatientWallet, Payment, Visit, WalletEntry
from app.models.enums import InvoiceStatus, WalletEntryKind
from app.models.ipd import Admission
from app.models.patient import Patient


@dataclass
class DiaryEntry:
    """One dated thing that moved money, whatever kind of thing it was."""

    kind: str                    # opd | ipd | wallet
    reference: str               # invoice or IP number, or the receipt
    date: Any
    description: str
    gross_paise: int = 0
    discount_paise: int = 0
    net_paise: int = 0
    received_paise: int = 0
    refunded_paise: int = 0
    balance_paise: int = 0       # what this entry alone still owes
    running_balance_paise: int = 0
    status: str = ""
    cancelled: bool = False
    #: An OPD bill settled against an inpatient stay is not collectable at
    #: the counter — it is already on the IPD bill. The old system marked
    #: these, and staff chase the wrong patient without it.
    credited_to_ipd: bool = False
    invoice_id: Optional[uuid.UUID] = None
    visit_id: Optional[uuid.UUID] = None
    admission_id: Optional[uuid.UUID] = None
    notes: List[str] = field(default_factory=list)


class DiaryService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def for_patient(
        self, patient_id: uuid.UUID, *, include_wallet: bool = True
    ) -> Optional[Dict[str, Any]]:
        patient = await self.session.get(Patient, patient_id)
        if patient is None:
            return None

        # Which of this patient's visits turned into an admission. An OPD
        # bill raised on such a visit is carried onto the inpatient bill, so
        # chasing it at the counter would be chasing money that is already
        # somewhere else.
        admitted_visits = set(
            (
                await self.session.execute(
                    select(Admission.visit_id).where(
                        Admission.patient_id == patient_id,
                        Admission.visit_id.is_not(None),
                    )
                )
            )
            .scalars()
            .all()
        )

        entries: List[DiaryEntry] = []
        entries += await self._invoices(patient_id, admitted_visits=admitted_visits)
        entries += await self._admissions(patient_id)
        if include_wallet:
            entries += await self._wallet(patient_id)

        # Oldest first to accumulate, newest first to read.
        entries.sort(key=lambda entry: (entry.date, entry.reference))
        running = 0
        for entry in entries:
            if not entry.cancelled:
                running += entry.balance_paise
            entry.running_balance_paise = running
        entries.reverse()

        live = [entry for entry in entries if not entry.cancelled]
        wallet_balance = await self.session.scalar(
            select(PatientWallet.balance_paise).where(
                PatientWallet.patient_id == patient_id
            )
        )

        return {
            "patient": {
                "id": patient.id,
                "uhid": patient.uhid,
                "name": patient.name,
                "age": patient.age,
                "gender": patient.gender.value,
                "phone_number": patient.phone_number,
            },
            "totals": {
                "gross_paise": sum(e.gross_paise for e in live),
                "discount_paise": sum(e.discount_paise for e in live),
                "net_paise": sum(e.net_paise for e in live),
                "received_paise": sum(e.received_paise for e in live),
                "refunded_paise": sum(e.refunded_paise for e in live),
                # The number the counter actually asks for. Wallet credit is
                # reported beside it rather than netted off: money the
                # patient has left with the hospital is not the same as money
                # they do not owe, and offsetting the two hides both.
                "outstanding_paise": running,
                "wallet_balance_paise": int(wallet_balance or 0),
                "visit_count": sum(1 for e in live if e.kind == "opd"),
                "admission_count": sum(1 for e in live if e.kind == "ipd"),
            },
            "entries": [entry.__dict__ for entry in entries],
        }

    # ------------------------------------------------------------------ OPD
    async def _invoices(
        self, patient_id: uuid.UUID, *, admitted_visits: Optional[set] = None
    ) -> List[DiaryEntry]:
        result = await self.session.execute(
            select(Invoice, Visit)
            .outerjoin(Visit, Visit.id == Invoice.visit_id)
            .options(selectinload(Invoice.payments))
            .where(Invoice.patient_id == patient_id)
        )

        entries: List[DiaryEntry] = []
        for invoice, visit in result.all():
            cancelled = invoice.status is InvoiceStatus.CANCELLED
            # Cancelled receipts contribute nothing: the money never moved.
            live_payments = [p for p in invoice.payments if p.cancelled_at is None]
            received = sum(p.amount_paise for p in live_payments if not p.is_refund)
            refunded = -sum(p.amount_paise for p in live_payments if p.is_refund)

            description = visit.visit_number if visit else "Counter bill"
            if invoice.doctor_name:
                description = f"{description} · {invoice.doctor_name}"

            entries.append(
                DiaryEntry(
                    kind="opd",
                    reference=invoice.invoice_number,
                    date=to_local(invoice.issued_at or invoice.created_at).date(),
                    description=description,
                    gross_paise=0 if cancelled else invoice.gross_paise,
                    discount_paise=0 if cancelled else invoice.discount_paise,
                    net_paise=0 if cancelled else invoice.total_paise,
                    received_paise=received,
                    refunded_paise=refunded,
                    balance_paise=0 if cancelled else invoice.total_paise - invoice.paid_paise,
                    status=invoice.status.value,
                    cancelled=cancelled,
                    credited_to_ipd=(
                        invoice.visit_id in (admitted_visits or set())
                        and invoice.visit_id is not None
                    ),
                    invoice_id=invoice.id,
                    visit_id=invoice.visit_id,
                    notes=list(invoice.pricing_notes or []),
                )
            )
        return entries

    # ------------------------------------------------------------------ IPD
    async def _admissions(self, patient_id: uuid.UUID) -> List[DiaryEntry]:
        """Inpatient stays.

        The final invoice, where there is one, is already listed as an OPD-
        shaped bill above — so the stay itself contributes the advance and
        the dates, not a second copy of the charges. Counting both would
        double the patient's balance, which is the single most damaging thing
        this screen could get wrong.
        """
        result = await self.session.execute(
            select(Admission).where(Admission.patient_id == patient_id)
        )

        entries: List[DiaryEntry] = []
        for admission in result.scalars():
            stay = f"Admitted {to_local(admission.admitted_at):%d %b}"
            if admission.discharged_at:
                stay += f" — discharged {to_local(admission.discharged_at):%d %b}"
            if admission.admitting_doctor_name:
                stay += f" · {admission.admitting_doctor_name}"

            entries.append(
                DiaryEntry(
                    kind="ipd",
                    reference=admission.ip_number,
                    date=to_local(admission.admitted_at).date(),
                    description=stay,
                    # An advance is money received against the stay. The
                    # charges themselves arrive on the final bill.
                    received_paise=admission.advance_paid_paise,
                    balance_paise=-admission.advance_paid_paise,
                    status=admission.status.value,
                    admission_id=admission.id,
                )
            )
        return entries

    # --------------------------------------------------------------- wallet
    async def _wallet(self, patient_id: uuid.UUID) -> List[DiaryEntry]:
        """Deposits and withdrawals only.

        Credit applied to a bill already shows on that bill as a payment;
        listing it here as well would count it twice. What belongs in the
        diary is money arriving at, or leaving, the counter.
        """
        result = await self.session.execute(
            select(WalletEntry)
            .where(
                WalletEntry.patient_id == patient_id,
                WalletEntry.kind.in_(
                    (WalletEntryKind.DEPOSIT, WalletEntryKind.WITHDRAWAL)
                ),
            )
        )

        entries: List[DiaryEntry] = []
        for entry in result.scalars():
            deposit = entry.amount_paise > 0
            entries.append(
                DiaryEntry(
                    kind="wallet",
                    reference=entry.receipt_number or "—",
                    date=to_local(entry.created_at).date(),
                    description=(
                        "Advance received" if deposit else "Advance returned"
                    ) + (f" · {entry.reason}" if entry.reason else ""),
                    received_paise=entry.amount_paise if deposit else 0,
                    refunded_paise=0 if deposit else -entry.amount_paise,
                    # An advance is not a charge, so it does not move what
                    # the patient owes — it moves what they have on account,
                    # reported separately.
                    balance_paise=0,
                    status=entry.kind.value,
                )
            )
        return entries
