"""Professional A4 invoice and payment receipt renderer."""
import io
from datetime import datetime
from typing import Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.models.emr import Invoice
from app.models.enums import InvoiceStatus
from app.models.patient import Patient
from app.printing.layout import (
    DEFAULT_LAYOUT,
    PageLayout,
    draw_letterhead,
    resolve_fonts,
    stamp_watermark,
)

PAGE_WIDTH, PAGE_HEIGHT = A4
BLUE = HexColor("#0B55A1")
INK = HexColor("#17212B")
MUTED = HexColor("#5B6875")
LIGHT = HexColor("#EEF3F9")
BORDER = HexColor("#D6E0EA")
GREEN = HexColor("#247A52")
RED = HexColor("#B6463A")


def _money(paise: int) -> str:
    return f"Rs. {paise / 100:,.2f}"


def _date(value: Optional[datetime]) -> str:
    return value.strftime("%d %b %Y, %I:%M %p") if value else "-"


def render_invoice_pdf(
    invoice: Invoice,
    patient: Patient,
    visit_number: Optional[str] = None,
    *,
    watermark: Optional[str] = None,
    layout: Optional[PageLayout] = None,
    brand: Optional[str] = None,
) -> bytes:
    """Render persisted invoice values without recalculating billing arithmetic.

    `brand` is the practice the bill is from: at a clinic housing two, a
    dental bill says Smile Dental. The site's own name when not given.

    A cancelled invoice is always stamped, whatever the caller asked for: a
    cancelled bill that prints identically to a live one is the kind of paper
    that gets paid twice. `watermark` is for the caller's own stamp — DUPLICATE
    on a reprint, most often.
    """
    layout = layout or DEFAULT_LAYOUT
    brand = brand or settings.HOSPITAL_NAME
    font, font_bold = resolve_fonts(layout.font_family)
    left = layout.content_left
    right_x = layout.content_right

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle(f"Invoice {invoice.invoice_number}")
    pdf.setAuthor(brand)

    draw_letterhead(pdf, layout)

    def text(x: float, y: float, value: str, size: float = 9, color=INK, bold=False):
        pdf.setFillColor(color)
        pdf.setFont(font_bold if bold else font, size)
        pdf.drawString(x, y, str(value))

    def right(x: float, y: float, value: str, size: float = 9, color=INK, bold=False):
        pdf.setFillColor(color)
        pdf.setFont(font_bold if bold else font, size)
        pdf.drawRightString(x, y, str(value))

    def line(y: float, color=BORDER, width=0.7):
        pdf.setStrokeColor(color)
        pdf.setLineWidth(width)
        pdf.line(left, y, right_x, y)

    # Letterhead
    y = layout.content_top
    text(left, y, brand.upper(), 20, BLUE, True)
    text(left, y - 17, "Trauma & Maternity Center", 9, MUTED)
    right(right_x, y, "TAX INVOICE / RECEIPT", 11, BLUE, True)
    right(right_x, y - 17, invoice.invoice_number, 9, MUTED)
    line(y - 31, BLUE, 1.3)

    # Invoice and patient metadata
    y -= 57
    text(left, y, "BILL TO", 8, MUTED, True)
    text(left, y - 17, patient.name, 11, INK, True)
    text(left, y - 32, f"UHID: {patient.uhid or '-'}", 9, MUTED)
    text(left, y - 46, f"Age / Gender: {patient.age} / {patient.gender.value}", 9, MUTED)
    text(left, y - 60, f"Mobile: {patient.phone_number}", 9, MUTED)

    right(right_x, y, "ISSUED", 8, MUTED, True)
    right(right_x, y - 17, _date(invoice.issued_at or invoice.created_at), 9)
    if visit_number:
        right(right_x, y - 32, f"Visit: {visit_number}", 9, MUTED)
    right(right_x, y - 47, f"Payer: {invoice.payer_type.value.replace('_', ' ').title()}", 9, MUTED)
    right(right_x, y - 62, f"Prepared by: {invoice.created_by_name or '-'}", 9, MUTED)

    # Itemized charges
    y -= 91
    pdf.setFillColor(LIGHT)
    pdf.roundRect(left, y - 22, layout.content_width, 24, 3, fill=1, stroke=0)
    text(left + 8, y - 14, "DESCRIPTION", 8, BLUE, True)
    right(365, y - 14, "QTY", 8, BLUE, True)
    right(445, y - 14, "RATE", 8, BLUE, True)
    right(right_x - 8, y - 14, "AMOUNT", 8, BLUE, True)
    y -= 42

    for item in invoice.lines:
        description = item.description[:55]
        text(left + 8, y, description, 9)
        # The code and the clerk's remark share the second line: the patient
        # who asks "what is this charge?" should find the answer on the bill
        # rather than have to ring the counter.
        below = " · ".join(
            part for part in (item.code, (item.remark or "")[:70]) if part
        )
        if below:
            text(left + 8, y - 12, below, 7.5, MUTED)
        right(365, y, item.quantity, 9)
        right(445, y, _money(item.unit_rate_paise), 9)
        right(right_x - 8, y, _money(item.total_paise), 9)
        y -= 25 if below else 19
        line(y + 7)

    # Totals summary uses stored invoice totals exactly.
    y -= 12
    summary_x = 345
    text(summary_x, y, "Gross", 9, MUTED)
    right(right_x - 8, y, _money(invoice.gross_paise), 9)
    y -= 17
    text(summary_x, y, "Discount", 9, MUTED)
    right(right_x - 8, y, f"- {_money(invoice.discount_paise)}", 9, RED)
    y -= 17
    text(summary_x, y, "Taxable value", 9, MUTED)
    right(right_x - 8, y, _money(invoice.taxable_paise), 9)
    y -= 17
    text(summary_x, y, "CGST + SGST", 9, MUTED)
    right(right_x - 8, y, _money(invoice.cgst_paise + invoice.sgst_paise), 9)
    if invoice.igst_paise:
        y -= 17
        text(summary_x, y, "IGST", 9, MUTED)
        right(right_x - 8, y, _money(invoice.igst_paise), 9)
    y -= 25
    pdf.setFillColor(BLUE)
    pdf.roundRect(summary_x - 8, y - 9, right_x - summary_x + 8, 28, 4, fill=1, stroke=0)
    text(summary_x, y, "TOTAL", 11, HexColor("#FFFFFF"), True)
    right(right_x - 8, y, _money(invoice.total_paise), 11, HexColor("#FFFFFF"), True)

    # Payment receipt block
    y -= 51
    text(left, y, "PAYMENT DETAILS", 8, MUTED, True)
    y -= 16
    payments = [payment for payment in invoice.payments if not payment.is_refund]
    refunds = [payment for payment in invoice.payments if payment.is_refund]
    if payments:
        for payment in payments:
            text(left, y, f"Receipt {payment.receipt_number}", 9, INK, True)
            text(190, y, payment.mode.value.replace("_", " ").title(), 9, MUTED)
            right(right_x, y, _money(payment.amount_paise), 9, GREEN, True)
            y -= 16
            if payment.reference:
                text(left, y, f"Reference: {payment.reference}", 8, MUTED)
                y -= 14
    else:
        text(left, y, "No payment recorded", 9, RED)
        y -= 16
    for payment in refunds:
        text(left, y, f"Refund {payment.receipt_number}", 8, RED)
        right(right_x, y, f"- {_money(payment.amount_paise)}", 8, RED)
        y -= 14

    y -= 3
    line(y)
    y -= 19
    text(left, y, "Paid", 9, MUTED)
    right(right_x, y, _money(invoice.paid_paise), 9, GREEN, True)
    y -= 17
    text(left, y, "Balance due", 10, INK, True)
    balance = invoice.total_paise - invoice.paid_paise
    right(right_x, y, _money(balance), 10, RED if balance > 0 else GREEN, True)

    y -= 42
    if invoice.discount_reason:
        text(left, y, f"Discount note: {invoice.discount_reason}", 8, MUTED)
        y -= 14
    text(left, y, "This is a computer-generated invoice. Please retain it for your records.", 8, MUTED)
    text(left, y - 14, f"Thank you for choosing {brand}.", 8, MUTED)
    right(right_x, y - 14, "Authorized signature", 8, MUTED)
    line(layout.content_bottom + 3, BLUE, 0.8)
    text(left, layout.content_bottom - 11,
         f"{brand} | Patient billing desk", 7.5, MUTED)
    right(right_x, layout.content_bottom - 11, invoice.status.value.upper(), 7.5, BLUE, True)

    stamp = "CANCELLED" if invoice.status is InvoiceStatus.CANCELLED else watermark
    if stamp:
        stamp_watermark(pdf, stamp)

    pdf.showPage()
    pdf.save()
    return output.getvalue()
