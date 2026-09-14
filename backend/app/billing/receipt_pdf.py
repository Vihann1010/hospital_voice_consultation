"""The standalone money receipt.

The invoice already prints what a patient was charged and what they have paid
so far. This is the other document: proof that a specific sum changed hands
at a specific moment.

It exists separately because three of the counter's transactions have no
invoice at all — an advance left on account, a balance handed back, and a
refund credited to the wallet. Before this, a patient handing over two
thousand rupees as a deposit walked away with nothing on paper, which is not
a defensible way to take money.

Amounts in words are printed alongside the figures for the same reason
cheques carry them: a digit can be altered after the fact and a sentence
cannot, quietly.
"""
import io
from datetime import datetime
from typing import Any, Mapping, Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.billing.payment_modes import summarise
from app.core.clock import to_local
from app.models.emr import Invoice
from app.models.enums import PaymentMode
from app.models.patient import Patient
from app.printing.layout import (
    DEFAULT_LAYOUT,
    PageLayout,
    draw_letterhead,
    resolve_fonts,
    stamp_watermark,
)

BLUE = HexColor("#0B55A1")
INK = HexColor("#17212B")
MUTED = HexColor("#5B6875")
LIGHT = HexColor("#EEF3F9")
BORDER = HexColor("#D6E0EA")
RED = HexColor("#B6463A")
WHITE = HexColor("#FFFFFF")

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _under_hundred(value: int) -> str:
    if value < 20:
        return _ONES[value]
    tens, ones = divmod(value, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def amount_in_words(paise: int) -> str:
    """Indian numbering: lakh and crore, not million.

    A receipt saying "One Million Rupees" in Kanpur would be read twice and
    trusted once.
    """
    rupees, paise_part = divmod(abs(int(paise)), 100)
    if rupees == 0:
        words = "Zero"
    else:
        groups = []
        crore, rest = divmod(rupees, 10_000_000)
        lakh, rest = divmod(rest, 100_000)
        thousand, rest = divmod(rest, 1_000)
        hundred, below = divmod(rest, 100)
        if crore:
            groups.append(f"{amount_in_words(crore * 100).replace(' Rupees Only', '')} Crore")
        if lakh:
            groups.append(f"{_under_hundred(lakh)} Lakh")
        if thousand:
            groups.append(f"{_under_hundred(thousand)} Thousand")
        if hundred:
            groups.append(f"{_ONES[hundred]} Hundred")
        if below:
            groups.append(_under_hundred(below))
        words = " ".join(groups)
    if paise_part:
        return f"{words} Rupees and {_under_hundred(paise_part)} Paise Only"
    return f"{words} Rupees Only"


def _money(paise: int) -> str:
    return f"Rs. {abs(paise) / 100:,.2f}"


def render_receipt_pdf(
    *,
    patient: Patient,
    receipt_number: str,
    amount_paise: int,
    mode: PaymentMode,
    received_at: datetime,
    received_by_name: str = "",
    mode_details: Optional[Mapping[str, Any]] = None,
    invoice: Optional[Invoice] = None,
    purpose: str = "Payment received",
    is_refund: bool = False,
    reason: Optional[str] = None,
    wallet_balance_paise: Optional[int] = None,
    layout: Optional[PageLayout] = None,
    watermark: Optional[str] = None,
) -> bytes:
    layout = layout or DEFAULT_LAYOUT
    font, font_bold = resolve_fonts(layout.font_family)
    left = layout.content_left
    right_x = layout.content_right

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle(f"Receipt {receipt_number}")
    pdf.setAuthor("Satya Hospital")

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

    y = layout.content_top
    text(left, y, "SATYA HOSPITAL", 20, BLUE, True)
    text(left, y - 17, "Trauma & Maternity Center", 9, MUTED)
    # A refund receipt must not be mistakable for a payment receipt at a
    # glance, so the heading changes rather than a line somewhere below.
    right(right_x, y, "REFUND VOUCHER" if is_refund else "MONEY RECEIPT", 11,
          RED if is_refund else BLUE, True)
    right(right_x, y - 17, receipt_number, 9, MUTED)
    line(y - 31, RED if is_refund else BLUE, 1.3)

    y -= 57
    text(left, y, "RECEIVED FROM" if not is_refund else "PAID TO", 8, MUTED, True)
    text(left, y - 17, patient.name, 12, INK, True)
    text(left, y - 33, f"UHID: {patient.uhid or '-'}", 9, MUTED)
    text(left, y - 47, f"Mobile: {patient.phone_number}", 9, MUTED)

    right(right_x, y, "DATE", 8, MUTED, True)
    right(right_x, y - 17, to_local(received_at).strftime("%d %b %Y, %I:%M %p"), 9)
    if invoice is not None:
        right(right_x, y - 33, f"Against: {invoice.invoice_number}", 9, MUTED)
    right(right_x, y - 47, f"Received by: {received_by_name or '-'}", 9, MUTED)

    # The figure, given the space it deserves.
    y -= 84
    pdf.setFillColor(LIGHT)
    pdf.roundRect(left, y - 34, layout.content_width, 56, 4, fill=1, stroke=0)
    text(left + 12, y, purpose.upper(), 8, MUTED, True)
    text(left + 12, y - 24, _money(amount_paise), 22, RED if is_refund else BLUE, True)
    instrument = summarise(mode, mode_details)
    right(right_x - 12, y - 6, instrument, 9, INK, True)
    # A cash deposit's reason defaults to the mode itself, and printing
    # "Cash" twice, one line under the other, just looks like a bug.
    if reason and reason.strip() != instrument:
        right(right_x - 12, y - 22, reason[:60], 8, MUTED)

    y -= 58
    text(left, y, "In words", 8, MUTED, True)
    text(left, y - 14, amount_in_words(amount_paise), 10, INK, True)

    if invoice is not None:
        y -= 42
        line(y + 10)
        text(left, y - 6, "Bill total", 9, MUTED)
        right(right_x, y - 6, _money(invoice.total_paise), 9)
        text(left, y - 22, "Paid to date", 9, MUTED)
        right(right_x, y - 22, _money(invoice.paid_paise), 9)
        text(left, y - 38, "Balance due", 9, MUTED, True)
        right(right_x, y - 38, _money(invoice.balance_paise), 9, INK, True)
        y -= 38

    if wallet_balance_paise is not None:
        y -= 34
        pdf.setFillColor(BLUE)
        pdf.roundRect(left, y - 9, layout.content_width, 28, 4, fill=1, stroke=0)
        text(left + 12, y, "WALLET BALANCE AFTER THIS", 9, WHITE, True)
        right(right_x - 12, y, _money(wallet_balance_paise), 11, WHITE, True)

    # Signatures. A refund needs two: the person paying out and the person
    # receiving, which is what makes a disputed payout answerable later.
    y -= 78
    line(y + 26)
    text(left, y + 10, "Cashier", 8, MUTED)
    text(left, y - 4, received_by_name or "", 9)
    if is_refund:
        right(right_x, y + 10, "Received by patient / attendant", 8, MUTED)
        pdf.setStrokeColor(BORDER)
        pdf.line(right_x - 150, y - 8, right_x, y - 8)

    text(left, layout.margin_bottom + 14,
         "Computer-generated receipt. Please retain for your records.", 7.5, MUTED)

    if watermark:
        stamp_watermark(pdf, watermark)

    pdf.showPage()
    pdf.save()
    return output.getvalue()
