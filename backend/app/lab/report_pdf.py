"""Printing a laboratory report.

Only verified results print. A test still on the bench is listed as pending
rather than left off, so a doctor reading the page knows it is coming and does
not assume it was never done. Each result prints the unit, method and
reference range that were stored when it was verified, never today's masters.

An abnormal value is printed in bold with its marker (L, H, LL, HH, or * for a
qualitative result outside what is expected). A value that was not compared —
no range applied — prints plain, with no marker, because an empty flag column
must mean "not flagged", never "normal by assumption".
"""
import io
from collections import OrderedDict
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

from app.core.clock import to_local
from app.lab.rules import ABNORMAL_FLAGS, FLAG_LABEL, SUSCEPTIBILITY
from app.printing.layout import DEFAULT_LAYOUT, PageLayout, draw_letterhead, resolve_fonts

BLUE = HexColor("#0B55A1")
INK = HexColor("#17212B")
MUTED = HexColor("#5B6875")
RULE = HexColor("#D6E0EA")
LIGHT = HexColor("#EEF3F9")


def _t(value: Any) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def _when(moment) -> str:
    return to_local(moment).strftime("%d %b %Y, %I:%M %p") if moment else "—"


def _sex(patient) -> str:
    value = getattr(patient.gender, "value", patient.gender)
    return {"male": "Male", "female": "Female"}.get(value, "Other")


def _styles(font: str, bold: str) -> Dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle("title", fontName=bold, fontSize=14, leading=18, textColor=BLUE, alignment=1),
        "label": ParagraphStyle("label", fontName=font, fontSize=8, leading=11, textColor=MUTED),
        "value": ParagraphStyle("value", fontName=bold, fontSize=9, leading=12, textColor=INK),
        "group": ParagraphStyle("group", fontName=bold, fontSize=10, leading=14, textColor=BLUE,
                                spaceBefore=10, spaceAfter=3),
        "test": ParagraphStyle("test", fontName=bold, fontSize=9.5, leading=13, textColor=INK,
                               spaceBefore=4, spaceAfter=2),
        "cell": ParagraphStyle("cell", fontName=font, fontSize=9, leading=11.5, textColor=INK),
        "cell_b": ParagraphStyle("cell_b", fontName=bold, fontSize=9, leading=11.5, textColor=INK),
        "head": ParagraphStyle("head", fontName=bold, fontSize=8, leading=10, textColor=MUTED),
        "small": ParagraphStyle("small", fontName=font, fontSize=8, leading=11, textColor=MUTED, spaceBefore=2),
        "amended": ParagraphStyle("amended", fontName=bold, fontSize=8.5, leading=11, textColor=INK, spaceBefore=2),
        "pending": ParagraphStyle("pending", fontName=font, fontSize=9, leading=13, textColor=MUTED, spaceBefore=3),
        "end": ParagraphStyle("end", fontName=font, fontSize=8, leading=11, textColor=MUTED, alignment=1),
        "sign": ParagraphStyle("sign", fontName=bold, fontSize=9, leading=12, textColor=INK, alignment=1),
        "sign_meta": ParagraphStyle("sign_meta", fontName=font, fontSize=8, leading=10.5, textColor=MUTED,
                                    alignment=1),
    }


def _results_table(rows: List[Dict[str, Any]], st, width: float) -> List[Any]:
    data = [[Paragraph("Investigation", st["head"]), Paragraph("Result", st["head"]),
             Paragraph("Unit", st["head"]), Paragraph("Reference range", st["head"])]]
    spans = []
    for row in rows:
        if not row.get("print", True):
            continue
        if row.get("result_type") == "heading":
            data.append([Paragraph(_t(row.get("name") or ""), st["cell_b"]), "", "", ""])
            spans.append(len(data) - 1)
            continue
        name = _t(row.get("name") or "")
        if row.get("method"):
            name += f"<br/><font size=7 color='#5B6875'>{_t(row['method'])}</font>"
        value = _t(row.get("value") or "—")
        flag = row.get("flag")
        if flag in ABNORMAL_FLAGS:
            cell = Paragraph(f"{value}&nbsp;&nbsp;{FLAG_LABEL.get(flag, '')}", st["cell_b"])
        else:
            cell = Paragraph(value, st["cell"])
        data.append([Paragraph(name, st["cell"]), cell, Paragraph(_t(row.get("unit") or ""), st["cell"]),
                     Paragraph(_t(row.get("reference_text") or ""), st["cell"])])
    table = Table(data, colWidths=[width * 0.38, width * 0.2, width * 0.14, width * 0.28], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]
    for index in spans:
        style.append(("SPAN", (0, index), (-1, index)))
    table.setStyle(TableStyle(style))
    return [table]


def _culture_block(culture: Dict[str, Any], st, width: float) -> List[Any]:
    out: List[Any] = []
    facts = []
    if culture.get("specimen"):
        facts.append(f"<b>Specimen:</b> {_t(culture['specimen'])}")
    if culture.get("incubation"):
        facts.append(f"<b>Incubation:</b> {_t(culture['incubation'])}")
    if facts:
        out.append(Paragraph("&nbsp;&nbsp;&nbsp;".join(facts), st["cell"]))
    if culture.get("growth") == "no_growth":
        out.append(Paragraph("<b>Result:</b> No growth", st["cell"]))
    for number, isolate in enumerate(culture.get("isolates") or [], start=1):
        heading = f"<b>Organism isolated{' ' + str(number) if len(culture.get('isolates') or []) > 1 else ''}:</b> " \
                  f"<i>{_t(isolate.get('organism') or '')}</i>"
        if isolate.get("colony_count"):
            heading += f"&nbsp;&nbsp;&nbsp;<b>Colony count:</b> {_t(isolate['colony_count'])}"
        out.append(Paragraph(heading, st["cell"]))
        data = [[Paragraph("Antibiotic", st["head"]), Paragraph("Interpretation", st["head"]),
                 Paragraph("MIC / zone", st["head"])]]
        for row in isolate.get("antibiotics") or []:
            label = SUSCEPTIBILITY.get(row.get("result"), row.get("result") or "")
            style = st["cell_b"] if row.get("result") == "R" else st["cell"]
            data.append([Paragraph(_t(row.get("name") or ""), st["cell"]), Paragraph(_t(label), style),
                         Paragraph(_t(row.get("value") or ""), st["cell"])])
        table = Table(data, colWidths=[width * 0.5, width * 0.25, width * 0.25], repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        out.append(Spacer(1, 3))
        out.append(table)
    if culture.get("comment"):
        out.append(Paragraph(f"<b>Comment:</b> {_t(culture['comment'])}", st["cell"]))
    return out


def render_lab_report(
    *, request, items, patient, admission=None, layout: Optional[PageLayout] = None
) -> bytes:
    layout = layout or DEFAULT_LAYOUT
    font, bold = resolve_fonts(layout.font_family)
    st = _styles(font, bold)
    width = layout.content_width
    output = io.BytesIO()

    def decorate(canvas, doc) -> None:
        draw_letterhead(canvas, layout)
        canvas.saveState()
        canvas.setFont(font, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(layout.content_right, max(layout.content_bottom - 12, 8),
                               f"{request.lab_number} · {patient.name} · Page {doc.page}")
        canvas.restoreState()

    frame = Frame(layout.content_left, layout.content_bottom, width,
                  layout.content_top - layout.content_bottom,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    template = BaseDocTemplate(output, pagesize=A4, title=f"Lab report {request.lab_number} — {patient.name}")
    template.addPageTemplates([PageTemplate(id="lab", frames=[frame], onPage=decorate)])

    ordered = sorted(items, key=lambda item: item.position)
    verified = [item for item in ordered if item.status == "verified"]
    reported = max((item.verified_at for item in verified), default=None)

    def pair(label: str, value: Any) -> List[Paragraph]:
        return [Paragraph(label, st["label"]), Paragraph(_t(value if value not in (None, "") else "—"), st["value"])]

    header = Table([
        pair("Patient", patient.name) + pair("Lab no.", request.lab_number),
        pair("Age / Sex", f"{patient.age} years / {_sex(patient)}") + pair("UHID", patient.uhid),
        pair("Referred by", request.referred_by) + pair("IP no.", admission.ip_number if admission else None),
        pair("Registered", _when(request.created_at)) + pair("Sample collected", _when(request.sample_collected_at)),
        pair("Reported", _when(reported)) + pair("Priority", (request.priority or "").title()),
    ], colWidths=[width * 0.15, width * 0.37, width * 0.17, width * 0.31])
    header.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story: List[Any] = [Paragraph("Laboratory Report", st["title"]), Spacer(1, 8), header]

    groups: "OrderedDict[str, List[Any]]" = OrderedDict()
    for item in ordered:
        if item.status == "cancelled":
            continue
        groups.setdefault(item.group_name or "General", []).append(item)

    for group, members in groups.items():
        story.append(Paragraph(_t(group.upper()), st["group"]))
        for item in members:
            if item.status != "verified":
                story.append(Paragraph(f"<b>{_t(item.name)}</b> — result pending", st["pending"]))
                continue
            block: List[Any] = [Paragraph(_t(item.name), st["test"])]
            if item.is_culture:
                block += _culture_block(item.culture or {}, st, width)
            else:
                block += _results_table(item.results or [], st, width)
            if item.remarks:
                block.append(Paragraph(f"<b>Remarks:</b> {_t(item.remarks)}", st["small"]))
            if item.critical_note:
                block.append(Paragraph(f"<b>Critical value informed:</b> {_t(item.critical_note)}", st["small"]))
            if (item.version or 1) > 1:
                last = (item.amendments or [{}])[-1]
                block.append(Paragraph(
                    f"Amended report (version {item.version}). Reason: {_t(last.get('reason') or '—')}",
                    st["amended"]))
            verifier = ", ".join(part for part in (
                item.verified_by_name, item.verifier_qualification,
                f"Reg. no. {item.verifier_registration}" if item.verifier_registration else None) if part)
            block.append(Paragraph(f"Verified by {_t(verifier)} on {_when(item.verified_at)}", st["small"]))
            story.append(KeepTogether(block))

    story += [Spacer(1, 16), Paragraph("— End of report —", st["end"]), Spacer(1, 26)]

    signers: "OrderedDict[str, tuple]" = OrderedDict()
    for item in verified:
        if item.verified_by_name:
            signers.setdefault(item.verified_by_name, (item.verifier_qualification, item.verifier_registration))
    if signers:
        cells = []
        for name, (qualification, registration) in list(signers.items())[:3]:
            lines = [Paragraph("_" * 28, st["sign_meta"]), Paragraph(_t(name), st["sign"])]
            if qualification:
                lines.append(Paragraph(_t(qualification), st["sign_meta"]))
            if registration:
                lines.append(Paragraph(f"Reg. no. {_t(registration)}", st["sign_meta"]))
            cells.append(lines)
        signatures = Table([cells], colWidths=[width / len(cells)] * len(cells))
        signatures.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(KeepTogether([signatures]))

    template.build(story)
    return output.getvalue()
