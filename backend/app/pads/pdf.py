"""Print a pad document on the hospital's letterhead.

Built on the shared print frame, so an OPD slip lines up with the bill and
the prescription printed on the same stationery. Uses ReportLab's flowables
rather than drawing at coordinates, because a pad's length depends entirely on
what the doctor wrote and a discharge summary routinely runs to three pages.

What prints is decided by the document's own section switches, as they stood
when it was signed — never by today's layout. Empty sections print nothing at
all rather than a heading over a blank space.
"""
import io
from datetime import datetime
from typing import Any, Dict, List, Optional
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.core.config import settings
from app.core.clock import to_local
from app.pads import sections as rules
from app.printing.layout import (
    DEFAULT_LAYOUT,
    PAGE_WIDTH,
    PageLayout,
    draw_letterhead,
    resolve_fonts,
    stamp_watermark,
)

BLUE = HexColor("#0B55A1")
INK = HexColor("#17212B")
MUTED = HexColor("#5B6875")
RULE = HexColor("#D6E0EA")
LIGHT = HexColor("#EEF3F9")


def _styles(font: str, bold: str, base: int) -> Dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle("title", fontName=bold, fontSize=base + 5, leading=base + 8,
                                textColor=BLUE, spaceAfter=2),
        "meta": ParagraphStyle("meta", fontName=font, fontSize=base - 0.5, leading=base + 3,
                               textColor=MUTED),
        "heading": ParagraphStyle("heading", fontName=bold, fontSize=base + 0.5,
                                  leading=base + 4, textColor=BLUE, spaceBefore=7, spaceAfter=2),
        "body": ParagraphStyle("body", fontName=font, fontSize=base, leading=base + 4,
                               textColor=INK),
        "bullet": ParagraphStyle("bullet", fontName=font, fontSize=base, leading=base + 4,
                                 textColor=INK, leftIndent=10, bulletIndent=1),
        "note": ParagraphStyle("note", fontName=font, fontSize=base - 1.5, leading=base + 1,
                               textColor=MUTED),
        "sign": ParagraphStyle("sign", fontName=bold, fontSize=base, leading=base + 4,
                               textColor=INK, alignment=2),
    }


def _text(value: Any) -> str:
    """Escape for ReportLab's mini-markup, keeping line breaks."""
    return escape(str(value)).replace("\n", "<br/>")


def _field_value(spec: Dict[str, Any], value: Any) -> Optional[str]:
    if value in (None, "", []):
        return None
    kind = spec.get("type")
    if kind == "checkbox":
        return "Yes" if value else None
    if kind == "multiselect":
        return ", ".join(str(item) for item in value)
    if kind == "date":
        try:
            return datetime.fromisoformat(str(value)).strftime("%d %b %Y")
        except ValueError:
            return str(value)
    text = str(value)
    return f"{text} {spec['unit']}" if spec.get("unit") else text


def _medicine_line(row: Dict[str, Any]) -> str:
    """One prescribed medicine as a single readable line.

    Nothing is invented to fill a gap: a medicine dictated without a duration
    prints without one, because a plausible-looking "for 5 days" nobody said
    is how a patient takes something for the wrong length of time.
    """
    head = " ".join(
        part for part in (row.get("name"), row.get("strength"), row.get("form")) if part
    )
    rest = [
        part
        for part in (
            row.get("dosage"),
            row.get("frequency_text") or row.get("frequency_code"),
            row.get("duration"),
            row.get("timing"),
            row.get("route"),
        )
        if part
    ]
    return f"{head} — {', '.join(rest)}" if rest else head


def _section_flowables(
    section: Dict[str, Any],
    value: Dict[str, Any],
    origin: Optional[Dict[str, Any]],
    styles: Dict[str, ParagraphStyle],
) -> List[Any]:
    body: List[Any] = [Paragraph(_text(section["title"]), styles["heading"])]
    kind = section["kind"]

    if kind == "fields":
        pairs = [
            (spec["label"], _field_value(spec, (value.get("fields") or {}).get(spec["key"])))
            for spec in section.get("fields", [])
        ]
        pairs = [(label, shown) for label, shown in pairs if shown]
        # Short fields such as vitals read best across the page, the way they
        # are written on paper: BP 130/80 · Pulse 88 · SpO2 98 %.
        body.append(
            Paragraph(
                " &nbsp;·&nbsp; ".join(
                    f"<font color='#5B6875'>{_text(label)}</font> {_text(shown)}"
                    for label, shown in pairs
                ),
                styles["body"],
            )
        )
    elif kind == "medicines":
        # Written the way a prescription is read aloud at the counter: the
        # drug first, then how much, how often and for how long.
        for row in value.get("medicines") or []:
            body.append(
                Paragraph(_text(_medicine_line(row)), styles["bullet"], bulletText="•")
            )
            if row.get("instructions"):
                body.append(Paragraph(_text(row["instructions"]), styles["note"]))
    elif kind == "investigations":
        for row in value.get("investigations") or []:
            line = row["name"]
            if row.get("note"):
                line += f" — {row['note']}"
            body.append(Paragraph(_text(line), styles["bullet"], bulletText="•"))
    else:
        if value.get("text"):
            body.append(Paragraph(_text(value["text"]), styles["body"]))
        for item in value.get("items") or []:
            body.append(Paragraph(_text(item), styles["bullet"], bulletText="•"))

    # Provenance travels onto paper. A reader of the signed copy is entitled
    # to know a section was first drafted by the intake model, even though a
    # doctor reviewed and signed it.
    source = str((origin or {}).get("source", ""))
    if source.startswith("ai:"):
        note = (
            "Drafted by AI from the ward record"
            if source == "ai:discharge_summary"
            else "Drafted from the patient's intake conversation"
        )
        note += "; edited by the doctor." if origin.get("edited") else "; reviewed by the doctor."
        body.append(Paragraph(note, styles["note"]))

    return [KeepTogether(body)]


def render_pad_pdf(
    *,
    document: Any,
    patient: Any,
    layout: Optional[PageLayout] = None,
    watermark: Optional[str] = None,
) -> bytes:
    layout = layout or DEFAULT_LAYOUT
    font, bold = resolve_fonts(layout.font_family)
    base = max(8, min(int(layout.font_size or 9), 13))
    styles = _styles(font, bold, base)

    output = io.BytesIO()
    frame = Frame(
        layout.content_left,
        layout.content_bottom,
        layout.content_width,
        layout.content_top - layout.content_bottom,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=14,
        id="content",
    )

    def decorate(canvas, doc) -> None:
        canvas.saveState()
        draw_letterhead(canvas, layout)
        canvas.setFont(font, 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(
            layout.content_right,
            layout.content_bottom - 2,
            f"{patient.name} · {patient.uhid or ''} · page {doc.page}",
        )
        canvas.restoreState()
        if watermark:
            stamp_watermark(canvas, watermark)

    template = BaseDocTemplate(
        output,
        pagesize=A4,
        title=f"{document.title} — {patient.name}",
        author=settings.HOSPITAL_NAME,
    )
    template.addPageTemplates([PageTemplate(id="pad", frames=[frame], onPage=decorate)])

    story: List[Any] = []
    story.append(Paragraph(_text(document.title), styles["title"]))
    if getattr(document, "serial_number", None):
        story.append(Paragraph(f"No. {_text(document.serial_number)}", styles["meta"]))

    moment = to_local(document.signed_at or document.created_at)
    gender = getattr(patient.gender, "value", patient.gender) or ""
    identity = Table(
        [[
            Paragraph(
                f"<b>{_text(patient.name)}</b> &nbsp; {_text(patient.age)} y / "
                f"{_text(str(gender).title())} &nbsp; · &nbsp; UHID {_text(patient.uhid or '—')}",
                styles["body"],
            ),
            Paragraph(_text(moment.strftime("%d %b %Y, %I:%M %p")), styles["meta"]),
        ]],
        colWidths=[layout.content_width * 0.7, layout.content_width * 0.3],
    )
    identity.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [identity, Spacer(1, 4)]

    if document.version > 1 and document.amendment_reason:
        story.append(Paragraph(
            f"Corrected version {document.version}. Reason: {_text(document.amendment_reason)}",
            styles["note"],
        ))

    printed_any = False
    for section in document.sections or []:
        if not section.get("visible_in_print", True):
            continue
        value = (document.values or {}).get(section["key"]) or {}
        if rules.is_empty(section, value):
            continue
        story += _section_flowables(
            section, value, (document.provenance or {}).get(section["key"]), styles
        )
        printed_any = True

    if not printed_any:
        story.append(Paragraph("Nothing on this document is set to print.", styles["meta"]))

    story.append(Spacer(1, 22))
    if document.signed_by_name:
        story.append(Paragraph(_text(document.signed_by_name), styles["sign"]))
        story.append(Paragraph(
            f"Signed {_text(to_local(document.signed_at).strftime('%d %b %Y, %I:%M %p'))}",
            ParagraphStyle("signed_at", parent=styles["note"], alignment=2),
        ))
    else:
        story.append(Paragraph("Not signed — draft for reading only", styles["sign"]))

    template.build(story)
    return output.getvalue()
