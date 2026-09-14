"""The surgery slip: the page that goes to theatre with the patient.

It is checked at the theatre door against the patient's wristband and the
consent form, so it prints the three things that must match — who, what, and
which side — larger than anything else on the page. The side is printed in
capitals on its own line; a slip where "Left" sits in a table cell beside
twenty other values is a slip nobody reads at 7 in the morning.
"""
import io
from typing import Any, List, Optional, Tuple

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.clock import to_local
from app.printing.layout import DEFAULT_LAYOUT, PageLayout, draw_letterhead, resolve_fonts

BLUE = HexColor("#0B55A1")
INK = HexColor("#17212B")
MUTED = HexColor("#5B6875")
RULE = HexColor("#D6E0EA")
LIGHT = HexColor("#EEF3F9")
RED = HexColor("#B6463A")


def render_surgery_slip(
    *,
    surgery: Any,
    patient: Any,
    admission: Optional[Any] = None,
    layout: Optional[PageLayout] = None,
) -> bytes:
    layout = layout or DEFAULT_LAYOUT
    font, bold = resolve_fonts(layout.font_family)
    left, right = layout.content_left, layout.content_right
    width = right - left

    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle(f"Surgery slip {surgery.ot_number}")
    pdf.setAuthor("Satya Hospital")
    draw_letterhead(pdf, layout)

    y = layout.content_top - 4

    def text(x, value, size=10, color=INK, weight=None):
        pdf.setFillColor(color)
        pdf.setFont(weight or font, size)
        pdf.drawString(x, y, str(value))

    # Title and OT number.
    text(left, "SURGERY SLIP", 16, BLUE, bold)
    pdf.setFont(bold, 16)
    pdf.drawRightString(right, y, surgery.ot_number)
    y -= 12
    pdf.setStrokeColor(BLUE)
    pdf.setLineWidth(1.2)
    pdf.line(left, y, right, y)
    y -= 22

    # Who.
    gender = getattr(getattr(patient, "gender", None), "value", "") if patient else ""
    text(left, patient.name if patient else "Unknown patient", 15, INK, bold)
    y -= 16
    who = f"{patient.age} y / {str(gender).title()}   ·   UHID {patient.uhid or '—'}" if patient else ""
    if admission is not None:
        who += f"   ·   {admission.ip_number}"
    text(left, who, 10, MUTED)
    y -= 26

    # What, and which side.
    pdf.setFillColor(LIGHT)
    pdf.rect(left, y - 46, width, 62, stroke=0, fill=1)
    text(left + 10, "OPERATION", 8, MUTED, bold)
    y -= 16
    text(left + 10, surgery.operation_name[:80], 14, INK, bold)
    y -= 22
    side = str(surgery.laterality).upper()
    text(left + 10, f"SIDE:  {side}", 16, RED if side in ("LEFT", "RIGHT", "BILATERAL") else INK, bold)
    y -= 34

    # The rest of the booking.
    scheduled = to_local(surgery.scheduled_at)
    rows: List[Tuple[str, str]] = [
        ("Diagnosis", surgery.diagnosis or "—"),
        ("Surgeon", surgery.surgeon_name),
        ("Assistants", ", ".join(surgery.assistants or []) or "—"),
        ("Anaesthetist", surgery.anaesthetist_name or "—"),
        ("Anaesthesia", surgery.anaesthesia_type or "—"),
        ("Theatre", surgery.room_name or "—"),
        ("Scheduled", f"{scheduled:%d %b %Y, %I:%M %p}  ·  about {surgery.expected_minutes} min"),
        ("Priority", str(surgery.priority).title()),
        ("Allergies", ", ".join((admission.allergies or []) if admission else []) or "None recorded"),
        ("Booked by", surgery.booked_by_name or "—"),
    ]
    for label, value in rows:
        text(left, label, 9, MUTED)
        colour = RED if label == "Allergies" and value != "None recorded" else INK
        text(left + 90, str(value)[:95], 10, colour, bold if label == "Allergies" and colour == RED else None)
        y -= 6
        pdf.setStrokeColor(RULE)
        pdf.setLineWidth(0.5)
        pdf.line(left, y, right, y)
        y -= 14

    # Checks at the theatre door.
    y -= 10
    text(left, "CHECKED AT THE THEATRE DOOR", 8, MUTED, bold)
    y -= 20
    for check in ("Identity matches wristband", "Consent form signed", "Site marked", "Side matches consent"):
        pdf.setStrokeColor(INK)
        pdf.rect(left, y - 2, 9, 9, stroke=1, fill=0)
        text(left + 16, check, 10)
        y -= 18

    # Signatures.
    y -= 30
    columns = ("Ward nurse", "Theatre nurse", "Anaesthetist")
    slot = width / len(columns)
    for index, label in enumerate(columns):
        x = left + index * slot
        pdf.setStrokeColor(MUTED)
        pdf.line(x + 6, y, x + slot - 12, y)
        pdf.setFillColor(MUTED)
        pdf.setFont(font, 8)
        pdf.drawString(x + 6, y - 11, label)

    pdf.showPage()
    pdf.save()
    return output.getvalue()
