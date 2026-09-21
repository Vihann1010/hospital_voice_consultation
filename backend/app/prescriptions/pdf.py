"""A4 prescription PDF.

Built with ReportLab's canvas rather than a template engine: a prescription is
a fixed, dense legal document where absolute placement is an advantage, and
ReportLab is pure Python (no system libraries), which keeps the container image
small and the build reproducible.

Layout is one page by default and flows onto continuation pages if the medicine
list is long, repeating the header and re-printing the patient identifiers so a
loose second page is never ambiguous.
"""
import io
import textwrap
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

try:
    from reportlab.lib.colors import Color, HexColor
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas as pdf_canvas
    _HAS_REPORTLAB = True
except ImportError:  # pragma: no cover - depends on deployment image
    _HAS_REPORTLAB = False

try:
    import qrcode
    _HAS_QRCODE = True
except ImportError:  # pragma: no cover
    _HAS_QRCODE = False


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
# The built-in Helvetica has no Devanagari glyphs, so any Hindi on the sheet —
# most often the general instructions, which are written in the patient's own
# language — came out as black boxes. Registering a font that covers
# Devanagari gives the glyphs, but not their order: without shaping, vowel
# signs print after their consonant and conjuncts fall apart. Every string is
# drawn with shaping on — see app/printing/fonts.py.
#
# Candidates are searched in preference order. Noto is the better typeface for
# Devanagari; FreeSans is the fallback because it ships in a smaller Debian
# package and is present on most images already.
from app.printing.fonts import SHAPE  # noqa: E402

_FONT_CANDIDATES = [
    (
        "SatyaSans",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
    ),
    (
        "SatyaSans",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ),
    (
        "SatyaSans",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ),
]

# Filled in by _register_fonts(); Helvetica remains the fallback so a missing
# font degrades to an English-only sheet rather than no sheet at all.
FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"


def _register_fonts() -> None:
    """Register a Devanagari-capable font family, once per process."""
    global FONT_REGULAR, FONT_BOLD, FONT_ITALIC
    if not _HAS_REPORTLAB or FONT_REGULAR != "Helvetica":
        return
    for name, regular_path, bold_path in _FONT_CANDIDATES:
        regular, bold = Path(regular_path), Path(bold_path)
        if not regular.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, str(regular)))
            bold_name = f"{name}-Bold"
            pdfmetrics.registerFont(
                TTFont(bold_name, str(bold if bold.exists() else regular))
            )
            pdfmetrics.registerFontFamily(name, normal=name, bold=bold_name,
                                          italic=name, boldItalic=bold_name)
        except Exception:  # noqa: BLE001 - try the next candidate
            logger.warning("font_registration_failed", extra={"font": regular_path})
            continue
        FONT_REGULAR = name
        FONT_BOLD = bold_name
        # This family has no true italic; the regular weight is far better
        # than falling back to Helvetica, which would drop Devanagari again.
        FONT_ITALIC = name
        logger.info("pdf_font_registered", extra={"font": regular_path})
        return
    logger.warning(
        "no_devanagari_font_found",
        extra={"detail": "Install fonts-freefont-ttf or fonts-noto-devanagari; "
                         "Hindi text will not render without it."},
    )


class PdfUnavailableError(RuntimeError):
    pass


# Brand palette, matching the web application.
# Palette from the Satya Trauma & Maternity Center logo.
PINE = "#0B55A1"          # logo blue
PINE_SOFT = "#1668BF"
MARIGOLD = "#6E8A05"      # darkened logo lime, legible as text on white
LIME = "#B7DC0D"          # logo lime, for fills only
INK = "#101C2B"
INK_MUTED = "#4A5A6E"
INK_FAINT = "#8496A8"
MINT = "#EEF3F9"
CLAY = "#C4553B"

MARGIN = 42
PAGE_WIDTH, PAGE_HEIGHT = (595.28, 841.89)  # A4 in points


@dataclass
class PrescriptionDocument:
    """Everything the sheet prints. Assembled by the service, not the renderer."""

    prescription_number: str
    issued_at: datetime
    department_label: str
    doctor_name: str
    doctor_qualification: Optional[str]
    doctor_registration: Optional[str]
    patient_name: str
    patient_age: Optional[int]
    patient_gender: Optional[str]
    patient_phone: Optional[str]
    patient_id_label: Optional[str]
    diagnosis: Optional[str]
    cause: Optional[str]
    chief_complaint: Optional[str]
    clinical_findings: Optional[str]
    investigations: List[str]
    medicines: List[Dict[str, Any]]
    general_instructions: Optional[str]
    follow_up: Optional[str]
    qr_payload: str
    signature_path: Optional[str] = None
    allergies: List[str] = None  # printed as a safety banner when present


_LOGO_CACHE = {"loaded": False, "image": None}


def _logo_image():
    """The brand mark for the letterhead, or None if the asset is missing."""
    if _LOGO_CACHE["loaded"]:
        return _LOGO_CACHE["image"]
    _LOGO_CACHE["loaded"] = True
    if settings.HOSPITAL_LOGO == "none":
        # The bundled mark belongs to one hospital. A site without its own
        # artwork prints its name instead (the typographic fallback below).
        return None
    try:
        path = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
        if path.exists():
            _LOGO_CACHE["image"] = ImageReader(str(path))
    except Exception:  # noqa: BLE001 - a missing logo must not block the sheet
        logger.warning("logo_load_failed")
    return _LOGO_CACHE["image"]


def _qr_image(payload: str):
    if not _HAS_QRCODE:
        return None
    try:
        qr = qrcode.QRCode(version=None, box_size=4, border=0,
                           error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(payload)
        qr.make(fit=True)
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)
        return ImageReader(buffer)
    except Exception:  # noqa: BLE001 - a missing QR must not block the prescription
        logger.warning("qr_generation_failed")
        return None


class _Renderer:
    def __init__(self, document: PrescriptionDocument) -> None:
        self.doc = document
        self.buffer = io.BytesIO()
        self.canvas = pdf_canvas.Canvas(self.buffer, pagesize=A4)
        self.canvas.setTitle(f"Prescription {document.prescription_number}")
        self.canvas.setAuthor(settings.HOSPITAL_NAME)
        self.canvas.setSubject(f"Prescription for {document.patient_name}")
        self.y = PAGE_HEIGHT - MARGIN
        self.page = 1
        self.qr = _qr_image(document.qr_payload)

    # -- primitives ---------------------------------------------------------
    def _text(self, x: float, y: float, value: str, *, font: Optional[str] = None,
              size: float = 9, color: str = INK) -> None:
        self.canvas.setFillColor(HexColor(color))
        self.canvas.setFont(font or FONT_REGULAR, size)
        self.canvas.drawString(x, y, value, **SHAPE)

    def _right_text(self, x: float, y: float, value: str, *, font: Optional[str] = None,
                    size: float = 9, color: str = INK) -> None:
        self.canvas.setFillColor(HexColor(color))
        self.canvas.setFont(font or FONT_REGULAR, size)
        self.canvas.drawRightString(x, y, value, **SHAPE)

    def _wrapped(self, x: float, y: float, value: str, width_chars: int, *,
                 font: Optional[str] = None, size: float = 9, leading: float = 11.5,
                 color: str = INK) -> float:
        lines = []
        for paragraph in (value or "").splitlines() or [""]:
            lines.extend(textwrap.wrap(paragraph, width_chars) or [""])
        for line in lines:
            self._text(x, y, line, font=font or FONT_REGULAR, size=size, color=color)
            y -= leading
        return y

    def _rule(self, y: float, *, color: str = "#D6E2DC", width: float = 0.7) -> None:
        self.canvas.setStrokeColor(HexColor(color))
        self.canvas.setLineWidth(width)
        self.canvas.line(MARGIN, y, PAGE_WIDTH - MARGIN, y)

    def _section_title(self, title: str) -> None:
        self._ensure_space(30)
        self.y -= 3
        self._text(MARGIN, self.y, title.upper(), font=FONT_BOLD, size=7.6,
                   color=INK_FAINT)
        self.y -= 3.5
        self._rule(self.y, color="#E3ECE8")
        self.y -= 9

    def _ensure_space(self, needed: float) -> None:
        if self.y - needed < MARGIN + 88:   # reserve the footer band
            self._footer(continued=True)
            self.canvas.showPage()
            self.page += 1
            self.y = PAGE_HEIGHT - MARGIN
            self._header(continuation=True)

    # -- blocks -------------------------------------------------------------
    def _header(self, *, continuation: bool = False) -> None:
        doc = self.doc
        # White letterhead band so the logo prints in its own colours; a thin
        # brand rule underneath keeps the sheet from looking unfinished.
        self.canvas.setFillColor(HexColor("#FFFFFF"))
        self.canvas.rect(0, PAGE_HEIGHT - 96, PAGE_WIDTH, 96, stroke=0, fill=1)
        self.canvas.setFillColor(HexColor(PINE))
        self.canvas.rect(0, PAGE_HEIGHT - 99, PAGE_WIDTH, 3, stroke=0, fill=1)
        self.canvas.setFillColor(HexColor(LIME))
        self.canvas.rect(0, PAGE_HEIGHT - 99, PAGE_WIDTH * 0.34, 3, stroke=0, fill=1)

        logo = _logo_image()
        if logo is not None:
            self.canvas.drawImage(logo, MARGIN, PAGE_HEIGHT - 78, width=132, height=64,
                                  preserveAspectRatio=True, anchor="sw", mask="auto")
        else:   # asset missing: fall back to a typographic wordmark
            self._text(MARGIN, PAGE_HEIGHT - 54, settings.HOSPITAL_NAME,
                       font=FONT_BOLD, size=14, color=PINE)

        self._text(MARGIN + 144, PAGE_HEIGHT - 56, f"Department of {doc.department_label}",
                   font=FONT_BOLD, size=9, color=PINE)
        self._text(MARGIN + 144, PAGE_HEIGHT - 68, settings.HOSPITAL_CITY,
                   font=FONT_REGULAR, size=7.5, color=INK_FAINT)

        self._right_text(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 46, doc.doctor_name,
                         font=FONT_BOLD, size=11, color=PINE)
        if doc.doctor_qualification:
            self._right_text(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 58, doc.doctor_qualification,
                             font=FONT_REGULAR, size=8, color=INK_MUTED)
        if doc.doctor_registration:
            self._right_text(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 69,
                             f"Reg. No. {doc.doctor_registration}",
                             font=FONT_REGULAR, size=7.5, color=INK_FAINT)
        self._right_text(PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 80,
                         f"Rx {doc.prescription_number}"
                         + (f"  ·  page {self.page}" if continuation else ""),
                         font=FONT_BOLD, size=7.5, color=MARIGOLD)

        self.y = PAGE_HEIGHT - 96 - 16

        if continuation:
            self._text(MARGIN, self.y, f"{doc.patient_name} — continued",
                       font=FONT_ITALIC, size=8.5, color=INK_MUTED)
            self.y -= 14

    def _patient_band(self) -> None:
        doc = self.doc
        height = 46
        self.canvas.setFillColor(HexColor(MINT))
        self.canvas.roundRect(MARGIN, self.y - height, PAGE_WIDTH - 2 * MARGIN, height,
                              5, stroke=0, fill=1)

        top = self.y - 15
        self._text(MARGIN + 12, top, doc.patient_name, font=FONT_BOLD, size=11.5,
                   color=PINE)
        bits = []
        if doc.patient_age is not None:
            bits.append(f"{doc.patient_age} yrs")
        if doc.patient_gender:
            bits.append(doc.patient_gender.capitalize())
        if doc.patient_phone:
            bits.append(doc.patient_phone)
        self._text(MARGIN + 12, top - 14, "  ·  ".join(bits), font=FONT_REGULAR, size=8.5,
                   color=INK_MUTED)
        if doc.patient_id_label:
            self._text(MARGIN + 12, top - 26, doc.patient_id_label, font=FONT_REGULAR,
                       size=7.5, color=INK_FAINT)

        self._right_text(PAGE_WIDTH - MARGIN - 12, top, "DATE", font=FONT_BOLD,
                         size=7, color=INK_FAINT)
        self._right_text(PAGE_WIDTH - MARGIN - 12, top - 13,
                         doc.issued_at.strftime("%d %b %Y, %I:%M %p"),
                         font=FONT_BOLD, size=9, color=INK)
        self.y -= height + 10

        if doc.allergies:
            banner = 18
            self.canvas.setFillColor(HexColor("#F7E7E2"))
            self.canvas.roundRect(MARGIN, self.y - banner, PAGE_WIDTH - 2 * MARGIN, banner,
                                  4, stroke=0, fill=1)
            self._text(MARGIN + 10, self.y - 13.5,
                       "ALLERGIES: " + ", ".join(doc.allergies).upper(),
                       font=FONT_BOLD, size=8, color=CLAY)
            self.y -= banner + 8

    def _clinical_block(self) -> None:
        doc = self.doc
        rows: List[Tuple[str, str]] = []
        if doc.chief_complaint:
            rows.append(("Chief complaint", doc.chief_complaint))
        if doc.clinical_findings:
            rows.append(("Clinical findings", doc.clinical_findings))
        if doc.diagnosis:
            rows.append(("Diagnosis", doc.diagnosis))
        if doc.cause:
            rows.append(("Cause", doc.cause))
        if not rows:
            return

        self._section_title("Clinical assessment")
        for label, value in rows:
            self._ensure_space(24)
            self._text(MARGIN, self.y, label, font=FONT_BOLD, size=8, color=INK_MUTED)
            emphasise = label in {"Diagnosis", "Cause"}
            end_y = self._wrapped(
                MARGIN + 96, self.y, value, 78,
                font=FONT_BOLD if emphasise else FONT_REGULAR,
                size=9.2 if emphasise else 9,
                color=PINE if emphasise else INK,
            )
            self.y = min(self.y - 11.5, end_y) - 1.5

    def _medicines_block(self) -> None:
        doc = self.doc
        self._section_title("Rx  —  Medicines")
        if not doc.medicines:
            self._text(MARGIN, self.y, "No medicines prescribed.", font=FONT_ITALIC,
                       size=9, color=INK_FAINT)
            self.y -= 16
            return

        # Column header
        self._ensure_space(26)
        self.canvas.setFillColor(HexColor("#F2F7F4"))
        self.canvas.rect(MARGIN, self.y - 4, PAGE_WIDTH - 2 * MARGIN, 16, stroke=0, fill=1)
        self._text(MARGIN + 6, self.y + 1, "#", font=FONT_BOLD, size=7.2, color=INK_FAINT)
        self._text(MARGIN + 22, self.y + 1, "MEDICINE", font=FONT_BOLD, size=7.2,
                   color=INK_FAINT)
        self._text(MARGIN + 250, self.y + 1, "DOSAGE & FREQUENCY", font=FONT_BOLD,
                   size=7.2, color=INK_FAINT)
        self._text(MARGIN + 420, self.y + 1, "DURATION", font=FONT_BOLD, size=7.2,
                   color=INK_FAINT)
        self.y -= 16

        for index, medicine in enumerate(doc.medicines, start=1):
            self._ensure_space(36)

            self._text(MARGIN + 6, self.y, str(index), font=FONT_BOLD, size=9,
                       color=MARIGOLD)

            title = " ".join(
                part for part in [medicine.get("form"), medicine.get("name")] if part
            )
            if medicine.get("strength"):
                title = f"{title} {medicine['strength']}"
            self._text(MARGIN + 22, self.y, title, font=FONT_BOLD, size=9.5, color=INK)

            frequency = " · ".join(
                part for part in [medicine.get("dosage"), medicine.get("frequency_text")
                                  or medicine.get("frequency_code")] if part
            )
            self._text(MARGIN + 250, self.y, frequency or "—", font=FONT_REGULAR, size=9,
                       color=INK)
            self._text(MARGIN + 420, self.y, medicine.get("duration") or "—",
                       font=FONT_REGULAR, size=9, color=INK)
            self.y -= 10.5

            detail_bits = []
            if medicine.get("generic"):
                detail_bits.append(medicine["generic"])
            if medicine.get("route"):
                detail_bits.append(medicine["route"])
            if detail_bits:
                self._text(MARGIN + 22, self.y, " · ".join(detail_bits),
                           font=FONT_ITALIC, size=7.6, color=INK_FAINT)
                self.y -= 8.5

            instruction_bits = [
                bit for bit in [medicine.get("timing"), medicine.get("instructions")] if bit
            ]
            if instruction_bits:
                self.y = self._wrapped(
                    MARGIN + 250, self.y + 3, " — ".join(instruction_bits), 52,
                    font=FONT_REGULAR, size=7.8, leading=9, color=INK_MUTED,
                )

            self.y -= 2.5
            self.canvas.setStrokeColor(HexColor("#EDF2EF"))
            self.canvas.setLineWidth(0.5)
            self.canvas.line(MARGIN + 22, self.y, PAGE_WIDTH - MARGIN, self.y)
            self.y -= 6.5

    def _investigations_block(self) -> None:
        if not self.doc.investigations:
            return
        self._section_title("Investigations advised")
        for item in self.doc.investigations:
            self._ensure_space(16)
            self._text(MARGIN + 6, self.y, "•", font=FONT_BOLD, size=9, color=MARIGOLD)
            self.y = self._wrapped(MARGIN + 18, self.y, item, 96, size=9, leading=10.5)

    def _instructions_block(self) -> None:
        doc = self.doc
        if not doc.general_instructions and not doc.follow_up:
            return
        self._section_title("Advice & follow-up")
        if doc.general_instructions:
            self.y = self._wrapped(MARGIN, self.y, doc.general_instructions, 104, size=9)
            self.y -= 4
        if doc.follow_up:
            self._ensure_space(20)
            self.canvas.setFillColor(HexColor("#FBF3E6"))
            self.canvas.roundRect(MARGIN, self.y - 16, PAGE_WIDTH - 2 * MARGIN, 20, 4,
                                  stroke=0, fill=1)
            self._text(MARGIN + 10, self.y - 10, f"Follow-up: {doc.follow_up}",
                       font=FONT_BOLD, size=9, color="#8A5A0E")
            self.y -= 28

    def _footer(self, *, continued: bool = False) -> None:
        doc = self.doc
        band_top = MARGIN + 78

        self.canvas.setStrokeColor(HexColor("#D6E2DC"))
        self.canvas.setLineWidth(0.7)
        self.canvas.line(MARGIN, band_top, PAGE_WIDTH - MARGIN, band_top)

        # QR + identifier
        if self.qr is not None:
            self.canvas.drawImage(self.qr, MARGIN, MARGIN + 6, width=58, height=58,
                                  preserveAspectRatio=True, mask="auto")
        self._text(MARGIN + (66 if self.qr is not None else 0), MARGIN + 50,
                   "PRESCRIPTION ID", font=FONT_BOLD, size=6.8, color=INK_FAINT)
        self._text(MARGIN + (66 if self.qr is not None else 0), MARGIN + 38,
                   doc.prescription_number, font=FONT_BOLD, size=10, color=PINE)
        self._text(MARGIN + (66 if self.qr is not None else 0), MARGIN + 26,
                   "Scan to verify this prescription", font=FONT_REGULAR, size=7,
                   color=INK_FAINT)

        # Signature
        signature_x = PAGE_WIDTH - MARGIN - 170
        if doc.signature_path:
            try:
                self.canvas.drawImage(doc.signature_path, signature_x, MARGIN + 34,
                                      width=150, height=38, preserveAspectRatio=True,
                                      anchor="sw", mask="auto")
            except Exception:  # noqa: BLE001 - fall back to the printed name
                logger.warning("signature_render_failed")
        self.canvas.setStrokeColor(HexColor("#9FB5AE"))
        self.canvas.setLineWidth(0.7)
        self.canvas.line(signature_x, MARGIN + 30, PAGE_WIDTH - MARGIN, MARGIN + 30)
        self._right_text(PAGE_WIDTH - MARGIN, MARGIN + 19, doc.doctor_name,
                         font=FONT_BOLD, size=9, color=INK)
        self._right_text(PAGE_WIDTH - MARGIN, MARGIN + 9,
                         doc.doctor_qualification or "Consultant", font=FONT_REGULAR,
                         size=7.5, color=INK_MUTED)

        if continued:
            self._text(MARGIN, MARGIN - 4, "continued on the next page…",
                       font=FONT_ITALIC, size=7, color=INK_FAINT)
        else:
            self._text(MARGIN, MARGIN - 4,
                       "This prescription is valid only for the named patient. "
                       "Do not share medicines.",
                       font=FONT_REGULAR, size=6.6, color=INK_FAINT)

    def render(self) -> bytes:
        self._header()
        self._patient_band()
        self._clinical_block()
        self._medicines_block()
        self._investigations_block()
        self._instructions_block()
        self._footer()
        self.canvas.showPage()
        self.canvas.save()
        return self.buffer.getvalue()


def render_prescription_pdf(document: PrescriptionDocument) -> bytes:
    if not _HAS_REPORTLAB:
        raise PdfUnavailableError(
            "PDF generation requires reportlab, which is not installed on this server."
        )
    _register_fonts()
    return _Renderer(document).render()


def pdf_capabilities() -> Dict[str, Any]:
    """What this node can render — surfaced by the health endpoint.

    `devanagari` false means Hindi on a prescription would be unreadable, so
    it is worth seeing before a patient is handed the sheet.
    """
    _register_fonts()
    return {
        "pdf": _HAS_REPORTLAB,
        "qr": _HAS_QRCODE,
        "devanagari": FONT_REGULAR != "Helvetica",
        "pdf_font": FONT_REGULAR,
    }
