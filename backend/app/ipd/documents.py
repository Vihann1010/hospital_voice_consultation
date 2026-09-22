"""Admission slip and stay ledger — the two IPD printouts Onito has that
this app did not: a slip handed over at admission, and a ledger of the
stay's charges and payments, either as a per-category summary or as every
line.

Same low-level canvas style as app/billing/pdf.py, on purpose: two
different-looking "hospital documents" printed on the same counter is the
kind of inconsistency a family notices even when they cannot name it.
"""
import io
from datetime import date, datetime
from typing import Any, Dict, Optional, Sequence

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.models.ipd import Admission, AdmissionCharge
from app.models.patient import Patient
from app.printing.layout import DEFAULT_LAYOUT, PageLayout, draw_letterhead, resolve_fonts

PAGE_WIDTH, PAGE_HEIGHT = A4
BLUE = HexColor("#0B55A1")
INK = HexColor("#17212B")
MUTED = HexColor("#5B6875")
LIGHT = HexColor("#EEF3F9")
BORDER = HexColor("#D6E0EA")
GREEN = HexColor("#247A52")
RED = HexColor("#B6463A")

CATEGORY_LABEL = {
    "bed": "Bed", "nursing": "Nursing", "doctor_visit": "Doctor visit",
    "procedure": "Procedure", "investigation": "Investigation", "medicine": "Medicine",
    "consumable": "Consumable", "oxygen": "Oxygen", "other": "Other",
}


def _money(paise: int) -> str:
    return f"Rs. {paise / 100:,.2f}"


def _date(value: Optional[datetime]) -> str:
    return value.strftime("%d %b %Y, %I:%M %p") if value else "-"


def _short_date(value: date) -> str:
    return value.strftime("%d %b %Y") if value else "-"


class _Writer:
    """The same text(), right() and line() helpers every renderer here needs,
    kept in one place so a new document does not reinvent them slightly
    differently each time."""

    def __init__(self, pdf: canvas.Canvas, layout: PageLayout):
        self.pdf = pdf
        self.layout = layout
        self.font, self.font_bold = resolve_fonts(layout.font_family)
        self.left = layout.content_left
        self.right_x = layout.content_right

    def text(self, x, y, value, size=9, color=INK, bold=False):
        self.pdf.setFillColor(color)
        self.pdf.setFont(self.font_bold if bold else self.font, size)
        self.pdf.drawString(x, y, str(value))

    def right(self, x, y, value, size=9, color=INK, bold=False):
        self.pdf.setFillColor(color)
        self.pdf.setFont(self.font_bold if bold else self.font, size)
        self.pdf.drawRightString(x, y, str(value))

    def line(self, y, color=BORDER, width=0.7):
        self.pdf.setStrokeColor(color)
        self.pdf.setLineWidth(width)
        self.pdf.line(self.left, y, self.right_x, y)


def render_admission_slip_pdf(
    admission: Admission,
    patient: Patient,
    *,
    ward_name: str,
    bed_label: str,
    organisation_name: Optional[str] = None,
    layout: Optional[PageLayout] = None,
) -> bytes:
    layout = layout or DEFAULT_LAYOUT
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle(f"Admission slip {admission.ip_number}")
    w = _Writer(pdf, layout)
    draw_letterhead(pdf, layout)

    y = layout.content_top
    w.text(w.left, y, "SATYA HOSPITAL", 20, BLUE, True)
    w.text(w.left, y - 17, "Trauma & Maternity Center", 9, MUTED)
    w.right(w.right_x, y, "ADMISSION SLIP", 11, BLUE, True)
    w.right(w.right_x, y - 17, admission.ip_number, 9, MUTED)
    w.line(y - 31, BLUE, 1.3)

    y -= 57
    w.text(w.left, y, "PATIENT", 8, MUTED, True)
    w.text(w.left, y - 17, patient.name, 12, INK, True)
    w.text(w.left, y - 33, f"UHID: {patient.uhid or '-'}", 9, MUTED)
    w.text(w.left, y - 47, f"Age / Gender: {patient.age} / {patient.gender.value}", 9, MUTED)
    w.text(w.left, y - 61, f"Mobile: {patient.phone_number}", 9, MUTED)

    w.right(w.right_x, y, "ADMITTED", 8, MUTED, True)
    w.right(w.right_x, y - 17, _date(admission.admitted_at), 9)
    w.right(w.right_x, y - 32, f"Ward / Bed: {ward_name} / {bed_label}", 9, MUTED)
    w.right(w.right_x, y - 47, f"Department: {admission.department.value.title()}", 9, MUTED)
    if organisation_name:
        w.right(w.right_x, y - 62, f"Paid by: {organisation_name}", 9, MUTED)

    y -= 92
    w.line(y)
    y -= 24
    w.text(w.left, y, "CARE TEAM", 8, MUTED, True)
    y -= 16
    w.text(w.left, y, f"Admitting doctor: {admission.admitting_doctor_name or '-'}", 9.5)
    if admission.other_consultant_name:
        y -= 15
        w.text(w.left, y, f"Other consultant: {admission.other_consultant_name}", 9.5)

    y -= 30
    w.line(y)
    y -= 24
    w.text(w.left, y, "CLINICAL", 8, MUTED, True)
    y -= 16
    w.text(w.left, y, f"Provisional diagnosis: {admission.provisional_diagnosis or '-'}", 9.5)
    y -= 15
    w.text(w.left, y, f"Reason for admission: {admission.reason_for_admission or '-'}", 9.5)
    y -= 15
    allergies = ", ".join(admission.allergies or []) or "None recorded"
    w.text(w.left, y, f"Allergies: {allergies}", 9.5)

    y -= 30
    w.line(y)
    y -= 24
    w.text(w.left, y, "ATTENDANT", 8, MUTED, True)
    y -= 16
    w.text(w.left, y, f"Name: {admission.attendant_name or '-'}", 9.5)
    y -= 15
    w.text(w.left, y, f"Mobile: {admission.attendant_phone or '-'}", 9.5)
    if admission.attendant_relation:
        y -= 15
        w.text(w.left, y, f"Relation: {admission.attendant_relation}", 9.5)
    if admission.attendant_address:
        y -= 15
        w.text(w.left, y, f"Address: {admission.attendant_address[:90]}", 9.5)

    y -= 40
    w.text(w.left, y, "Patient / attendant signature", 8, MUTED)
    w.right(w.right_x, y, "Admitting staff signature", 8, MUTED)
    w.line(layout.content_bottom + 3, BLUE, 0.8)
    w.text(w.left, layout.content_bottom - 11,
           "Satya Hospital | Inpatient admission desk", 7.5, MUTED)

    pdf.showPage()
    pdf.save()
    return output.getvalue()


def render_ledger_pdf(
    admission: Admission,
    patient: Patient,
    *,
    charges: Sequence[AdmissionCharge],
    deposits: Sequence[Any],
    summary: Dict[str, Any],
    detailed: bool,
    layout: Optional[PageLayout] = None,
) -> bytes:
    """Onito's summary and detailed ledger, from the same data.

    Summary collapses charges to one line per category, using running_bill's
    own grouping so the total on this document can never drift from the
    total the ward screen already showed staff before they printed it.
    """
    layout = layout or DEFAULT_LAYOUT
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    kind = "Detailed ledger" if detailed else "Summary ledger"
    pdf.setTitle(f"{kind} {admission.ip_number}")
    w = _Writer(pdf, layout)
    draw_letterhead(pdf, layout)

    y = layout.content_top
    w.text(w.left, y, "SATYA HOSPITAL", 20, BLUE, True)
    w.text(w.left, y - 17, "Trauma & Maternity Center", 9, MUTED)
    w.right(w.right_x, y, kind.upper(), 11, BLUE, True)
    w.right(w.right_x, y - 17, admission.ip_number, 9, MUTED)
    w.line(y - 31, BLUE, 1.3)

    y -= 57
    w.text(w.left, y, patient.name, 12, INK, True)
    w.text(w.left, y - 16, f"UHID: {patient.uhid or '-'} · {admission.department.value.title()}", 9, MUTED)
    w.right(w.right_x, y, f"Admitted {_date(admission.admitted_at)}", 9, MUTED)
    if admission.discharged_at:
        w.right(w.right_x, y - 15, f"Discharged {_date(admission.discharged_at)}", 9, MUTED)

    y -= 45
    w.line(y)
    y -= 24

    if detailed:
        w.text(w.left, y, "CHARGES", 8, MUTED, True)
        y -= 16
        pdf.setFillColor(LIGHT)
        pdf.roundRect(w.left, y - 6, w.right_x - w.left, 20, 3, fill=1, stroke=0)
        w.text(w.left + 6, y, "DATE", 7.5, BLUE, True)
        w.text(w.left + 70, y, "DESCRIPTION", 7.5, BLUE, True)
        w.right(390, y, "QTY", 7.5, BLUE, True)
        w.right(465, y, "RATE", 7.5, BLUE, True)
        w.right(w.right_x - 6, y, "AMOUNT", 7.5, BLUE, True)
        y -= 22
        for charge in charges:
            if y < layout.content_bottom + 60:
                pdf.showPage()
                draw_letterhead(pdf, layout)
                y = layout.content_top
            w.text(w.left, y, _short_date(charge.charged_on), 8.5)
            w.text(w.left + 70, y, charge.description[:42], 8.5)
            w.right(390, y, str(charge.quantity), 8.5)
            w.right(465, y, _money(charge.unit_rate_paise), 8.5)
            w.right(w.right_x - 6, y, _money(charge.total_paise), 8.5)
            y -= 16
        y -= 8
    else:
        w.text(w.left, y, "CHARGES BY CATEGORY", 8, MUTED, True)
        y -= 16
        for category, values in sorted(summary["by_category"].items()):
            label = CATEGORY_LABEL.get(category, category.replace("_", " ").title())
            w.text(w.left, y, f"{label} ({values['count']})", 9.5)
            w.right(w.right_x, y, _money(values["total_paise"]), 9.5, bold=True)
            y -= 17

    y -= 4
    w.line(y)
    y -= 19
    w.text(w.left, y, "Total charges", 10, INK, True)
    w.right(w.right_x, y, _money(summary["total_paise"]), 10, INK, True)

    y -= 30
    w.text(w.left, y, "PAYMENTS", 8, MUTED, True)
    y -= 16
    if deposits:
        for entry in deposits:
            if y < layout.content_bottom + 40:
                pdf.showPage()
                draw_letterhead(pdf, layout)
                y = layout.content_top
            label = f"Receipt {entry.receipt_number}" if entry.receipt_number else "Advance"
            mode = entry.mode.value.replace("_", " ").title() if entry.mode else ""
            w.text(w.left, y, label, 9, INK, True)
            w.text(230, y, mode, 9, MUTED)
            w.right(w.right_x, y, _money(entry.amount_paise), 9, GREEN, True)
            y -= 16
    else:
        w.text(w.left, y, "No payment recorded", 9, RED)
        y -= 16

    y -= 4
    w.line(y)
    y -= 19
    w.text(w.left, y, "Total paid", 9, MUTED)
    w.right(w.right_x, y, _money(summary["advance_held_paise"]), 9, GREEN, True)
    y -= 17
    w.text(w.left, y, "Balance", 10, INK, True)
    balance = summary["total_paise"] - summary["advance_held_paise"]
    w.right(w.right_x, y, _money(balance), 10, RED if balance > 0 else GREEN, True)

    w.line(layout.content_bottom + 3, BLUE, 0.8)
    w.text(w.left, layout.content_bottom - 11, "Satya Hospital | Inpatient billing", 7.5, MUTED)
    w.right(w.right_x, layout.content_bottom - 11,
            "" if admission.final_invoice_id else "Running balance — not a final bill",
            7.5, MUTED)

    pdf.showPage()
    pdf.save()
    return output.getvalue()
