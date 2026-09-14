"""Printing certificates and consent forms.

A certificate is a letter: its number, the date, one or two sentences in
fixed wording, and the doctor's name, qualification and registration number
above a line for signature and seal. A consent form is a record of a
conversation: what was proposed, the risks and alternatives named, the
declaration in English and in Hindi, and signature lines for the patient or
guardian and a witness — signed on paper, because that is what the law and
the patient both recognise.

If this server cannot shape Devanagari, the Hindi declaration is left off and
the form says so, rather than printing Hindi nobody can read.
"""
import io
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

from app.core.clock import local_today, to_local
from app.pads import forms
from app.pads.defaults import document_type as type_spec
from app.printing.fonts import SHAPE, SHAPING, can_print_hindi, devanagari_fonts
from app.printing.layout import DEFAULT_LAYOUT, PageLayout, draw_letterhead, stamp_watermark

BLUE = HexColor("#0B55A1")
INK = HexColor("#17212B")
MUTED = HexColor("#5B6875")
RULE = HexColor("#D6E0EA")
LIGHT = HexColor("#EEF3F9")


def _t(value: Any) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def _styles(font: str, bold: str) -> Dict[str, ParagraphStyle]:
    shaping = 1 if SHAPING and font != "Helvetica" else 0

    def style(name: str, **kwargs: Any) -> ParagraphStyle:
        made = ParagraphStyle(name, **kwargs)
        if "shaping" in ParagraphStyle.defaults:
            made.shaping = shaping
        return made

    return {
        "title": style("title", fontName=bold, fontSize=15, leading=19, textColor=BLUE, alignment=1),
        "title_hi": style("title_hi", fontName=bold, fontSize=12.5, leading=18, textColor=BLUE, alignment=1),
        "meta": style("meta", fontName=font, fontSize=9, leading=12, textColor=MUTED),
        "meta_r": style("meta_r", fontName=font, fontSize=9, leading=12, textColor=MUTED, alignment=2),
        "heading": style("heading", fontName=bold, fontSize=10, leading=14, textColor=BLUE,
                         spaceBefore=8, spaceAfter=2),
        "body": style("body", fontName=font, fontSize=10, leading=14.5, textColor=INK),
        "letter": style("letter", fontName=font, fontSize=11.5, leading=19, textColor=INK,
                        spaceAfter=8, firstLineIndent=0),
        "bullet": style("bullet", fontName=font, fontSize=10, leading=14, textColor=INK,
                        leftIndent=14, bulletIndent=2),
        "hindi": style("hindi", fontName=font, fontSize=10.5, leading=16, textColor=INK,
                       leftIndent=14, bulletIndent=2),
        "label": style("label", fontName=font, fontSize=8.5, leading=11, textColor=MUTED),
        "sign": style("sign", fontName=bold, fontSize=10.5, leading=14, textColor=INK, alignment=2),
        "sign_meta": style("sign_meta", fontName=font, fontSize=9, leading=12, textColor=MUTED, alignment=2),
        "note": style("note", fontName=font, fontSize=8, leading=11, textColor=MUTED),
    }


def _field_text(spec: Dict[str, Any], value: Any) -> Optional[str]:
    kind = spec.get("type")
    if kind == "checkbox":
        return "Yes" if value else "No"
    if value in (None, "", []):
        return None
    if kind == "date":
        return forms.show_date(value)
    if kind == "multiselect":
        return ", ".join(str(item) for item in value)
    return str(value)


def _doctor_lines(document: Any, doctor: Any) -> List[str]:
    if not document.signed_by_name:
        return []
    lines = [document.signed_by_name]
    if doctor is not None and getattr(doctor, "qualification", None):
        lines.append(doctor.qualification)
    if doctor is not None and getattr(doctor, "registration_number", None):
        lines.append(f"Reg. No. {doctor.registration_number}")
    return lines


def _header(document: Any, spec: Any, styles: Dict[str, ParagraphStyle], width: float,
            hindi: bool) -> List[Any]:
    story: List[Any] = [Paragraph(_t(spec.label.upper() if spec.family == "certificate" else spec.label),
                                  styles["title"])]
    if hindi and spec.family == "consent" and document.document_type in forms.TITLE_HI:
        story.append(Paragraph(_t(forms.TITLE_HI[document.document_type]), styles["title_hi"]))
    issued = to_local(document.signed_at).strftime("%d %b %Y") if document.signed_at else "Not signed"
    number = document.serial_number or "Number given when signed"
    row = Table(
        [[Paragraph(f"No. {_t(number)}", styles["meta"]), Paragraph(f"Date: {_t(issued)}", styles["meta_r"])]],
        colWidths=[width / 2, width / 2],
    )
    row.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [Spacer(1, 6), row, Spacer(1, 10)]
    if document.version > 1 and document.amendment_reason:
        story.append(Paragraph(
            f"Corrected version {document.version}. Reason: {_t(document.amendment_reason)}", styles["note"]
        ))
        story.append(Spacer(1, 4))
    return story


def _certificate(document: Any, patient: Any, admission: Any, doctor: Any,
                 styles: Dict[str, ParagraphStyle]) -> List[Any]:
    issued_on = to_local(document.signed_at).date() if document.signed_at else local_today()
    story: List[Any] = [Spacer(1, 10)]
    for line in forms.certificate_paragraphs(
        document.document_type, document.values or {}, patient=patient, issued_on=issued_on,
        ip_number=getattr(admission, "ip_number", None),
    ):
        story.append(Paragraph(_t(line), styles["letter"]))
    story.append(Spacer(1, 48))
    doctor_lines = _doctor_lines(document, doctor)
    if doctor_lines:
        story.append(Paragraph("Signature and seal", styles["sign_meta"]))
        story.append(Spacer(1, 2))
        story.append(Paragraph(_t(doctor_lines[0]), styles["sign"]))
        for line in doctor_lines[1:]:
            story.append(Paragraph(_t(line), styles["sign_meta"]))
    else:
        story.append(Paragraph("Not signed — draft for reading only", styles["sign"]))
    story += [Spacer(1, 30), Paragraph("Not valid for medico-legal purposes.", styles["note"])]
    return story


def _identity(patient: Any, admission: Any, styles: Dict[str, ParagraphStyle], width: float) -> Table:
    gender = getattr(getattr(patient, "gender", None), "value", "") or ""
    cells = [
        f"<b>{_t(patient.name)}</b>",
        f"{_t(patient.age)} y / {_t(str(gender).title())}",
        f"UHID {_t(patient.uhid or '—')}",
    ]
    if admission is not None:
        cells.append(f"IP {_t(admission.ip_number)}")
    table = Table([[Paragraph(" &nbsp;·&nbsp; ".join(cells), styles["body"])]], colWidths=[width])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _consent(document: Any, patient: Any, admission: Any, doctor: Any,
             styles: Dict[str, ParagraphStyle], width: float, hindi: bool) -> List[Any]:
    values = document.values or {}
    story: List[Any] = [_identity(patient, admission, styles, width), Spacer(1, 4)]

    for section in document.sections or []:
        key = section["key"]
        if key == "consent_by":
            continue
        if section["kind"] == "fields":
            given = forms.fields(values, key)
            rows = []
            for spec in section.get("fields", []):
                shown = _field_text(spec, given.get(spec["key"]))
                if shown is None:
                    continue
                rows.append([Paragraph(_t(spec["label"]), styles["label"]), Paragraph(_t(shown), styles["body"])])
            if rows:
                story.append(Paragraph(_t(section["title"]), styles["heading"]))
                table = Table(rows, colWidths=[width * 0.38, width * 0.62])
                table.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(table)
        else:
            value = values.get(key) or {}
            items = [item for item in value.get("items") or [] if str(item).strip()]
            text = str(value.get("text") or "").strip()
            if not items and not text:
                continue
            story.append(Paragraph(_t(section["title"]), styles["heading"]))
            if text:
                story.append(Paragraph(_t(text), styles["body"]))
            for item in items:
                story.append(Paragraph(_t(item), styles["bullet"], bulletText="•"))

    wording = forms.STATEMENTS.get(document.document_type, {})
    story.append(Paragraph("Declaration", styles["heading"]))
    for number, line in enumerate(wording.get("en", []), start=1):
        story.append(Paragraph(_t(line), styles["bullet"], bulletText=f"{number}."))
    if hindi:
        story.append(Paragraph(_t("घोषणा"), styles["heading"]))
        for number, line in enumerate(wording.get("hi", []), start=1):
            story.append(Paragraph(_t(line), styles["hindi"], bulletText=f"{number}."))
    else:
        story.append(Paragraph(
            "The Hindi declaration could not be printed on this server. Explain the form in the "
            "patient's language and record the language below.", styles["note"]))

    given = forms.fields(values, "consent_by")
    language = given.get("language_other") if given.get("language") == "Other" else given.get("language")
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Explained in: <b>{_t(language or '—')}</b>", styles["body"]))
    clause = forms.guardian_clause(values)
    if clause:
        story.append(Paragraph(_t(clause), styles["body"]))

    consenting = (given.get("guardian_name") if given.get("consent_given_by") == forms.GUARDIAN
                  else patient.name) or ""

    def block(role: str, name: str) -> List[Any]:
        english, hindi_label = forms.SIGNATURE_LABELS[role]
        label = f"{english}<br/>{_t(hindi_label)}" if hindi else english
        name_en, name_hi = forms.SIGNATURE_LABELS["name"]
        when_en, when_hi = forms.SIGNATURE_LABELS["when"]
        return [
            Spacer(1, 34),
            Paragraph("_" * 38, styles["label"]),
            Paragraph(label, styles["label"]),
            Paragraph(f"{name_en}{' / ' + _t(name_hi) if hindi else ''}: {_t(name)}", styles["body"]),
            Paragraph(f"{when_en}{' / ' + _t(when_hi) if hindi else ''}: ____________________", styles["body"]),
        ]

    witness = given.get("witness_name") or ""
    if given.get("witness_relation"):
        witness += f" ({given['witness_relation']})"
    grid = Table([[block("patient", consenting), block("witness", witness)]],
                 colWidths=[width / 2, width / 2])
    grid.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(KeepTogether([grid]))

    doctor_lines = _doctor_lines(document, doctor)
    story.append(Spacer(1, 18))
    if doctor_lines:
        story.append(Paragraph(
            "Explained by: <b>" + _t(doctor_lines[0]) + "</b>" +
            "".join(f" · {_t(line)}" for line in doctor_lines[1:]) +
            " &nbsp;&nbsp; Signature: ____________________", styles["body"]))
    else:
        story.append(Paragraph("Not signed in the system — draft for reading only.", styles["sign"]))
    if given.get("interpreter_name"):
        story.append(Paragraph(
            f"Interpreter: {_t(given['interpreter_name'])} &nbsp;&nbsp; Signature: ____________________",
            styles["body"]))
    story += [Spacer(1, 10), Paragraph(
        "This form is valid only when signed by the patient or guardian and a witness. "
        "A new form is needed for a different operation or treatment.", styles["note"])]
    return story


def render_form_pdf(
    *,
    document: Any,
    patient: Any,
    admission: Any = None,
    doctor: Any = None,
    layout: Optional[PageLayout] = None,
    watermark: Optional[str] = None,
) -> bytes:
    spec = type_spec(document.document_type)
    if spec is None or not spec.family:
        raise ValueError(f"{document.document_type} is not a certificate or consent form")
    layout = layout or DEFAULT_LAYOUT
    font, bold = devanagari_fonts()
    styles = _styles(font, bold)
    hindi = can_print_hindi()
    width = layout.content_width

    output = io.BytesIO()
    frame = Frame(layout.content_left, layout.content_bottom, width,
                  layout.content_top - layout.content_bottom,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=14, id="content")

    def decorate(canvas, doc) -> None:
        canvas.saveState()
        draw_letterhead(canvas, layout)
        canvas.setFont(font, 7)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(layout.content_right, layout.content_bottom - 2,
                               f"{patient.name} · UHID {patient.uhid or '—'} · "
                               f"{document.serial_number or 'Draft'} · page {doc.page}", **SHAPE)
        canvas.restoreState()
        if watermark:
            stamp_watermark(canvas, watermark)

    template = BaseDocTemplate(output, pagesize=A4, title=f"{spec.label} — {patient.name}",
                               author="Satya Hospital")
    template.addPageTemplates([PageTemplate(id="form", frames=[frame], onPage=decorate)])

    story = _header(document, spec, styles, width, hindi)
    if spec.family == "certificate":
        story += _certificate(document, patient, admission, doctor, styles)
    else:
        story += _consent(document, patient, admission, doctor, styles, width, hindi)
    template.build(story)
    return output.getvalue()
