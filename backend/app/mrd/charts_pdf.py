"""Pages the records bundle prints that no screen prints.

The admission record that opens the file, the contents page, the vitals chart
and the drug administration record. The charts exist as structured data on
the ward screens; on paper they are tables, one row per observation and one
row per dose, exactly as recorded — nothing is recomputed or summarised,
because the file is a record of what was done, not an analysis of it.
"""
import io
from datetime import date, datetime
from typing import Any, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.core.clock import to_local
from app.printing.fonts import SHAPE, SHAPING, devanagari_fonts
from app.printing.layout import DEFAULT_LAYOUT, PageLayout, draw_letterhead

BLUE = HexColor("#0B55A1")
INK = HexColor("#17212B")
MUTED = HexColor("#5B6875")
RULE = HexColor("#D6E0EA")
LIGHT = HexColor("#EEF3F9")
MARGIN = 36


def _t(value: Any) -> str:
    return escape("" if value is None else str(value)).replace("\n", "<br/>")


def _styles():
    font, bold = devanagari_fonts()
    shaping = 1 if SHAPING and font != "Helvetica" else 0

    def style(name: str, **kwargs: Any) -> ParagraphStyle:
        made = ParagraphStyle(name, **kwargs)
        if "shaping" in ParagraphStyle.defaults:
            made.shaping = shaping
        return made

    return font, bold, {
        "title": style("title", fontName=bold, fontSize=15, leading=19, textColor=BLUE),
        "heading": style("heading", fontName=bold, fontSize=10.5, leading=14, textColor=BLUE,
                         spaceBefore=10, spaceAfter=3),
        "body": style("body", fontName=font, fontSize=9.5, leading=13, textColor=INK),
        "small": style("small", fontName=font, fontSize=7.8, leading=10, textColor=INK),
        "small_b": style("small_b", fontName=bold, fontSize=7.8, leading=10, textColor=INK),
        "label": style("label", fontName=font, fontSize=8.5, leading=11, textColor=MUTED),
        "note": style("note", fontName=font, fontSize=8, leading=11, textColor=MUTED),
    }


def _local(moment: Optional[datetime], fmt: str = "%d %b %Y, %I:%M %p") -> str:
    return to_local(moment).strftime(fmt) if moment else "—"


ROUTE_LABEL = {"iv": "IV", "im": "IM", "sc": "SC", "nasogastric": "Ryles tube"}


def _label(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw).replace("_", " ").capitalize() if raw else "—"


def _identity(patient: Any, admission: Any) -> str:
    gender = getattr(getattr(patient, "gender", None), "value", "") or ""
    return (f"{patient.name} · {patient.age} y / {str(gender).title()} · UHID {patient.uhid or '—'} · "
            f"{admission.ip_number}")


def _build(story: List[Any], *, title: str, patient: Any, admission: Any, layout: PageLayout,
           wide: bool = False) -> bytes:
    """A document with the letterhead (portrait) or a plain running header (landscape charts)."""
    font, _bold, _ = _styles()
    output = io.BytesIO()
    size = landscape(A4) if wide else A4
    width, height = size
    if wide:
        frame = Frame(MARGIN, MARGIN, width - 2 * MARGIN, height - 2 * MARGIN - 26,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=6)
    else:
        frame = Frame(layout.content_left, layout.content_bottom, layout.content_width,
                      layout.content_top - layout.content_bottom,
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=14)

    def decorate(canvas, doc) -> None:
        canvas.saveState()
        if wide:
            canvas.setFont(font, 8)
            canvas.setFillColor(MUTED)
            canvas.drawString(MARGIN, height - MARGIN - 6, f"{title} — {_identity(patient, admission)}", **SHAPE)
            canvas.setStrokeColor(RULE)
            canvas.line(MARGIN, height - MARGIN - 12, width - MARGIN, height - MARGIN - 12)
            canvas.drawRightString(width - MARGIN, MARGIN - 18, f"page {doc.page}")
        else:
            draw_letterhead(canvas, layout)
            canvas.setFont(font, 7)
            canvas.setFillColor(MUTED)
            canvas.drawRightString(layout.content_right, layout.content_bottom - 2,
                                   f"{_identity(patient, admission)} · page {doc.page}", **SHAPE)
        canvas.restoreState()

    template = BaseDocTemplate(output, pagesize=size, title=f"{title} — {patient.name}",
                               author=settings.HOSPITAL_NAME)
    template.addPageTemplates([PageTemplate(id="page", frames=[frame], onPage=decorate)])
    template.build(story)
    return output.getvalue()


def _grid(rows: List[List[Any]], widths: Sequence[float], *, header_rows: int = 1,
          extra: Sequence[Tuple] = ()) -> Table:
    table = Table(rows, colWidths=list(widths), repeatRows=header_rows)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, header_rows - 1), LIGHT),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        *extra,
    ]))
    return table


# ------------------------------------------------------------------ cover
def render_cover_pdf(*, admission: Any, patient: Any, occupancies: Sequence[Any], surgeries: Sequence[Any],
                     attendant: Optional[str] = None, layout: Optional[PageLayout] = None) -> bytes:
    layout = layout or DEFAULT_LAYOUT
    _font, _bold, styles = _styles()
    width = layout.content_width
    gender = getattr(getattr(patient, "gender", None), "value", "") or ""
    address = ", ".join(part for part in (patient.address, patient.city, patient.state, patient.pincode) if part)
    guardian = f"{patient.guardian_relation or ''} {patient.guardian_name}".strip() if patient.guardian_name else "—"

    def pairs(items: List[Tuple[str, Any]]) -> Table:
        rows = [[Paragraph(_t(label), styles["label"]), Paragraph(_t(value if value not in (None, "") else "—"), styles["body"])]
                for label, value in items]
        return _grid(rows, [width * 0.3, width * 0.7], header_rows=0)

    story: List[Any] = [
        Paragraph("MEDICAL RECORD — INPATIENT", styles["title"]),
        Paragraph(f"{_t(admission.ip_number)} · {_t(patient.name)}", styles["heading"]),
        Paragraph("Patient", styles["heading"]),
        pairs([
            ("Name", f"{' '.join(p for p in (patient.title, patient.name) if p)}"),
            ("Age / sex", f"{patient.age} years / {str(gender).title()}"),
            ("UHID", patient.uhid), ("Phone", patient.phone_number), ("Guardian", guardian),
            ("Address", address), ("Blood group", patient.blood_group),
        ]),
        Paragraph("Admission", styles["heading"]),
        pairs([
            ("IP number", admission.ip_number),
            ("Department", _label(admission.department)),
            ("Admission type", _label(admission.admission_type)),
            ("Admitting doctor", admission.admitting_doctor_name),
            ("Admitted", _local(admission.admitted_at)),
            ("Discharged", _local(admission.discharged_at) if admission.discharged_at else "Still admitted"),
            ("Discharge type", _label(admission.discharge_type) if admission.discharge_type else "—"),
            ("Reason for admission", admission.reason_for_admission),
            ("Provisional diagnosis", admission.provisional_diagnosis),
            ("Final diagnosis", admission.final_diagnosis),
            ("Allergies", ", ".join(admission.allergies or []) or "None recorded"),
            ("Attendant", attendant),
        ]),
    ]
    if occupancies:
        story.append(Paragraph("Beds", styles["heading"]))
        rows = [[Paragraph(h, styles["small_b"]) for h in ("Ward", "Bed", "From", "To", "Reason for move")]]
        for stay in occupancies:
            rows.append([Paragraph(_t(stay.ward_name), styles["small"]), Paragraph(_t(stay.bed_label), styles["small"]),
                         Paragraph(_local(stay.started_at), styles["small"]),
                         Paragraph(_local(stay.ended_at) if stay.ended_at else "—", styles["small"]),
                         Paragraph(_t(stay.transfer_reason or ""), styles["small"])])
        story.append(_grid(rows, [width * f for f in (0.22, 0.1, 0.22, 0.22, 0.24)]))
    if surgeries:
        story.append(Paragraph("Operations", styles["heading"]))
        rows = [[Paragraph(h, styles["small_b"]) for h in ("OT number", "Operation", "Side", "Surgeon", "Date", "Status")]]
        for case in surgeries:
            rows.append([Paragraph(_t(case.ot_number), styles["small"]), Paragraph(_t(case.operation_name), styles["small"]),
                         Paragraph(_t(case.laterality), styles["small"]), Paragraph(_t(case.surgeon_name), styles["small"]),
                         Paragraph(_local(case.scheduled_at, "%d %b %Y"), styles["small"]),
                         Paragraph(_label(case.status), styles["small"])])
        story.append(_grid(rows, [width * f for f in (0.14, 0.32, 0.1, 0.2, 0.12, 0.12)]))
    return _build(story, title="Medical record", patient=patient, admission=admission, layout=layout)


# --------------------------------------------------------------- contents
def render_contents_pdf(*, admission: Any, patient: Any, entries: Sequence[Tuple[str, str, str, int]],
                        skipped: Sequence[Tuple[str, str]] = (), generated_by: str = "",
                        date_range: str = "", layout: Optional[PageLayout] = None) -> bytes:
    """entries: (section, title, date, first page)."""
    layout = layout or DEFAULT_LAYOUT
    _font, _bold, styles = _styles()
    width = layout.content_width
    story: List[Any] = [Paragraph("Contents", styles["title"])]
    if date_range:
        story.append(Paragraph(_t(date_range), styles["note"]))
    story.append(Spacer(1, 6))
    rows = [[Paragraph(h, styles["small_b"]) for h in ("Section", "Document", "Date", "Page")]]
    for section, title, when, page in entries:
        rows.append([Paragraph(_t(section), styles["small"]), Paragraph(_t(title), styles["small"]),
                     Paragraph(_t(when), styles["small"]), Paragraph(str(page), styles["small"])])
    story.append(_grid(rows, [width * f for f in (0.2, 0.52, 0.18, 0.1)]))
    if skipped:
        story.append(Paragraph("Not included", styles["heading"]))
        for title, reason in skipped:
            story.append(Paragraph(f"• {_t(title)} — {_t(reason)}", styles["body"]))
    story += [Spacer(1, 10), Paragraph(
        f"Compiled by {_t(generated_by)} on {_t(datetime.now().astimezone().strftime('%d %b %Y, %I:%M %p'))}. "
        "Unsigned documents are stamped DRAFT.", styles["note"])]
    return _build(story, title="Contents", patient=patient, admission=admission, layout=layout)


def _in_range(moment: Optional[datetime], date_from: Optional[date], date_to: Optional[date]) -> bool:
    if moment is None:
        return True
    on = to_local(moment).date()
    return (date_from is None or on >= date_from) and (date_to is None or on <= date_to)


# ----------------------------------------------------------------- vitals
def render_vitals_pdf(*, admission: Any, patient: Any, records: Sequence[Any], date_from: Optional[date] = None,
                      date_to: Optional[date] = None, layout: Optional[PageLayout] = None) -> bytes:
    _font, _bold, styles = _styles()
    width = landscape(A4)[0] - 2 * MARGIN
    heads = ("Recorded", "BP", "Pulse", "RR", "SpO2", "O2", "Temp °F", "AVPU", "Pain", "Sugar", "Urine ml",
             "NEWS2", "By", "Escalation")
    rows = [[Paragraph(h, styles["small_b"]) for h in heads]]
    shown = [record for record in sorted(records, key=lambda r: r.recorded_at)
             if _in_range(record.recorded_at, date_from, date_to)]
    for record in shown:
        temp = f"{record.temperature_c * 9 / 5 + 32:.1f}" if record.temperature_c is not None else ""
        bp = f"{record.systolic_bp}/{record.diastolic_bp}" if record.systolic_bp else ""
        oxygen = (f"{record.oxygen_litres:g} L" if record.oxygen_litres else "Yes") if record.on_oxygen else ""
        news = f"{record.news2_score} {record.news2_risk or ''}".strip() if record.news2_score is not None else ""
        cells = [_local(record.recorded_at, "%d %b %H:%M"), bp, record.pulse, record.respiratory_rate,
                 record.spo2_percent, oxygen, temp, record.consciousness, record.pain_score,
                 record.blood_sugar_mgdl, record.urine_output_ml, news, record.recorded_by_name,
                 record.escalation_note if record.escalated else ""]
        rows.append([Paragraph(_t(value), styles["small"]) for value in cells])
    fractions = (0.09, 0.06, 0.045, 0.04, 0.045, 0.05, 0.055, 0.045, 0.04, 0.05, 0.06, 0.07, 0.12, 0.19)
    story: List[Any] = [Paragraph("Vitals chart", styles["title"]), Spacer(1, 4)]
    if len(rows) == 1:
        story.append(Paragraph("No observations recorded in the chosen dates.", styles["body"]))
    else:
        story.append(_grid(rows, [width * f for f in fractions]))
    return _build(story, title="Vitals chart", patient=patient, admission=admission,
                  layout=layout or DEFAULT_LAYOUT, wide=True)


# ------------------------------------------------------ drug administration
def render_mar_pdf(*, admission: Any, patient: Any, orders: Sequence[Any], date_from: Optional[date] = None,
                   date_to: Optional[date] = None, layout: Optional[PageLayout] = None) -> bytes:
    _font, _bold, styles = _styles()
    width = landscape(A4)[0] - 2 * MARGIN
    rows = [[Paragraph(h, styles["small_b"]) for h in ("Due", "Outcome", "At", "By", "Reason / notes")]]
    extra: List[Tuple] = []
    for order in sorted(orders, key=lambda o: o.started_at):
        doses = [dose for dose in sorted(order.administrations, key=lambda d: d.due_at)
                 if _in_range(dose.due_at, date_from, date_to)
                 and (dose.was_given is not None or to_local(dose.due_at) <= to_local(datetime.now().astimezone()))]
        if not doses and not _in_range(order.started_at, date_from, date_to):
            continue
        heading = (f"{order.drug_name} {order.strength or ''} · {order.dose} · {ROUTE_LABEL.get(order.route.value, _label(order.route))} · "
                   f"{order.frequency_code}{' · STAT' if order.is_stat else ''}{' · SOS' if order.is_sos else ''} — "
                   f"ordered by {order.ordered_by_name} {_local(order.started_at, '%d %b %H:%M')}; "
                   f"{_label(order.status)}"
                   f"{' ' + _local(order.stopped_at, '%d %b %H:%M') + ' (' + (order.stop_reason or '') + ')' if order.stopped_at else ''}")
        extra += [("SPAN", (0, len(rows)), (-1, len(rows))), ("BACKGROUND", (0, len(rows)), (-1, len(rows)), LIGHT)]
        rows.append([Paragraph(_t(heading), styles["small_b"]), "", "", "", ""])
        if not doses:
            rows.append([Paragraph("No doses due in the chosen dates.", styles["small"]), "", "", "", ""])
            extra.append(("SPAN", (0, len(rows) - 1), (-1, len(rows) - 1)))
        for dose in doses:
            outcome = "Given" if dose.was_given else ("Not given" if dose.was_given is False else "Not recorded")
            rows.append([Paragraph(_local(dose.due_at, "%d %b %H:%M"), styles["small"]),
                         Paragraph(outcome, styles["small_b"] if dose.was_given is not True else styles["small"]),
                         Paragraph(_local(dose.given_at, "%d %b %H:%M") if dose.given_at else "", styles["small"]),
                         Paragraph(_t(dose.given_by_name), styles["small"]),
                         Paragraph(_t(" · ".join(part for part in (dose.omission_reason, dose.notes) if part)), styles["small"])])
    story: List[Any] = [Paragraph("Drug administration record", styles["title"]), Spacer(1, 4)]
    if len(rows) == 1:
        story.append(Paragraph("No medicines ordered in the chosen dates.", styles["body"]))
    else:
        story.append(_grid(rows, [width * f for f in (0.14, 0.12, 0.14, 0.2, 0.4)], extra=extra))
    return _build(story, title="Drug administration record", patient=patient, admission=admission,
                  layout=layout or DEFAULT_LAYOUT, wide=True)


# ------------------------------------------------------------- file pages
def stamp_file_pages(data: bytes, label: str) -> bytes:
    """Number every page of the bound file.

    Each document keeps its own footer ("page 1" of a consent form), which
    is right when it is printed alone and wrong inside the bundle, where the
    contents page gives positions in the whole file. The file page number,
    bottom left, is the one the contents page refers to.
    """
    from pypdf import PdfReader, PdfWriter

    font, _bold = devanagari_fonts()
    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()
    total = len(reader.pages)
    for number, page in enumerate(reader.pages, start=1):
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        overlay = io.BytesIO()
        stamp = pdf_canvas.Canvas(overlay, pagesize=(width, height))
        stamp.setFont(font, 7)
        stamp.setFillColor(MUTED)
        stamp.drawString(MARGIN, 14, f"{label} · file page {number} of {total}", **SHAPE)
        stamp.save()
        page.merge_page(PdfReader(io.BytesIO(overlay.getvalue())).pages[0])
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


# ----------------------------------------------------------------- images
def render_image_pdf(*, data: bytes, title: str, caption: str) -> bytes:
    """An uploaded image on its own A4 page (each frame of a multi-page TIFF)."""
    from PIL import Image, ImageSequence

    font, bold = devanagari_fonts()
    output = io.BytesIO()
    page = pdf_canvas.Canvas(output, pagesize=A4)
    width, height = A4
    with Image.open(io.BytesIO(data)) as picture:
        for frame in ImageSequence.Iterator(picture):
            image = frame.convert("RGB")
            page.setFont(bold, 10)
            page.setFillColor(INK)
            page.drawString(MARGIN, height - MARGIN, title[:110], **SHAPE)
            page.setFont(font, 8)
            page.setFillColor(MUTED)
            page.drawString(MARGIN, height - MARGIN - 13, caption[:150], **SHAPE)
            box_w, box_h = width - 2 * MARGIN, height - 2 * MARGIN - 30
            scale = min(box_w / image.width, box_h / image.height, 1.0 if image.width > 600 else 3.0)
            draw_w, draw_h = image.width * scale, image.height * scale
            page.drawImage(ImageReader(image), MARGIN + (box_w - draw_w) / 2, MARGIN + (box_h - draw_h),
                           draw_w, draw_h)
            page.showPage()
    page.save()
    return output.getvalue()
