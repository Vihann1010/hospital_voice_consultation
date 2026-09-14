"""Shared printing primitives: page geometry, letterhead, watermarks, merging.

Every printed document in the hospital used to carry its own copy of the page
size, the margins and the fonts, which is how two documents printed on the
same letterhead end up disagreeing about where the text starts. This is the
one place that knows.

Nothing here draws a document. It gives a renderer the frame to draw inside —
where the content may go once the letterhead has taken its space, how to stamp
a reprint, and how to bind several finished PDFs into one file.
"""
import io
import os
from dataclasses import dataclass
from typing import List, Optional, Sequence

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# A4 in points, which is what ReportLab measures in.
PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89


@dataclass(frozen=True)
class PageLayout:
    """The frame a document is drawn inside, resolved from its settings."""

    margin_top: int = 42
    margin_bottom: int = 42
    margin_left: int = 42
    margin_right: int = 42
    font_family: str = "Helvetica"
    font_size: int = 9
    header_image: Optional[str] = None
    header_height: int = 0
    footer_image: Optional[str] = None
    footer_height: int = 0
    footer_remark: Optional[str] = None
    watermark_duplicates: bool = True

    @property
    def content_left(self) -> float:
        return self.margin_left

    @property
    def content_right(self) -> float:
        return PAGE_WIDTH - self.margin_right

    @property
    def content_width(self) -> float:
        return self.content_right - self.content_left

    @property
    def content_top(self) -> float:
        """Where a document may start writing, below any letterhead."""
        return PAGE_HEIGHT - self.margin_top - self.header_height

    @property
    def content_bottom(self) -> float:
        """The floor. Writing below this collides with the footer."""
        return self.margin_bottom + self.footer_height


DEFAULT_LAYOUT = PageLayout()


def layout_from(setting: Optional[object]) -> PageLayout:
    """Turn a PrintSetting row into a layout, falling back to the defaults.

    Takes the row rather than importing the model, so this module stays
    usable from anywhere without dragging the ORM in behind it.
    """
    if setting is None:
        return DEFAULT_LAYOUT
    return PageLayout(
        margin_top=getattr(setting, "margin_top", 42),
        margin_bottom=getattr(setting, "margin_bottom", 42),
        margin_left=getattr(setting, "margin_left", 42),
        margin_right=getattr(setting, "margin_right", 42),
        font_family=getattr(setting, "font_family", "Helvetica"),
        font_size=getattr(setting, "font_size", 9),
        header_image=getattr(setting, "header_image", None),
        header_height=getattr(setting, "header_height", 0),
        footer_image=getattr(setting, "footer_image", None),
        footer_height=getattr(setting, "footer_height", 0),
        footer_remark=getattr(setting, "footer_remark", None),
        watermark_duplicates=getattr(setting, "watermark_duplicates", True),
    )


def resolve_fonts(family: str) -> tuple:
    """The regular and bold face to actually draw with.

    The family comes from a settings row, so it can name a font this server
    does not have. Falling back to Helvetica prints a slightly wrong-looking
    bill; trusting the value prints nothing at all, because ReportLab raises
    when asked for a face it cannot find. A wrong-looking bill is recoverable.
    """
    from reportlab.pdfbase import pdfmetrics

    available = set(pdfmetrics.getRegisteredFontNames())
    regular = family if family in available else "Helvetica"
    bold = f"{regular}-Bold"
    if bold not in available:
        bold = "Helvetica-Bold" if regular == "Helvetica" else regular
    return regular, bold


async def load_layout(session, document_type: str) -> PageLayout:
    """The layout configured for a document type, or the defaults."""
    from sqlalchemy import select

    from app.models.printing import PrintSetting

    setting = (
        await session.execute(
            select(PrintSetting).where(PrintSetting.document_type == document_type)
        )
    ).scalar_one_or_none()
    return layout_from(setting)


def branding_path(filename: Optional[str]) -> Optional[str]:
    """Resolve a letterhead image, refusing anything outside the branding folder.

    The filename comes from a settings row an administrator edits, so it is
    treated as untrusted input: a path that escapes the branding directory
    would let a configuration change read arbitrary files off the server.
    """
    if not filename:
        return None
    root = os.path.realpath(os.path.join(settings.MEDIA_ROOT, "branding"))
    candidate = os.path.realpath(os.path.join(root, filename))
    if os.path.commonpath([root, candidate]) != root:
        # Not "filename": logging reserves that attribute on LogRecord and
        # raises rather than overwriting it, which would turn this rejection
        # into a crash on the very path that is supposed to fail safely.
        logger.warning("branding_path_rejected", extra={"branding_file": filename})
        return None
    return candidate if os.path.isfile(candidate) else None


def draw_letterhead(canvas, layout: PageLayout) -> None:
    """Paint the header and footer images, if this document has them."""
    from reportlab.lib.utils import ImageReader

    header = branding_path(layout.header_image)
    if header and layout.header_height:
        canvas.drawImage(
            ImageReader(header),
            layout.content_left,
            PAGE_HEIGHT - layout.margin_top - layout.header_height,
            width=layout.content_width,
            height=layout.header_height,
            preserveAspectRatio=True,
            anchor="n",
            mask="auto",
        )

    footer = branding_path(layout.footer_image)
    if footer and layout.footer_height:
        canvas.drawImage(
            ImageReader(footer),
            layout.content_left,
            layout.margin_bottom,
            width=layout.content_width,
            height=layout.footer_height,
            preserveAspectRatio=True,
            anchor="s",
            mask="auto",
        )

    if layout.footer_remark:
        canvas.saveState()
        canvas.setFont(layout.font_family, 7)
        canvas.setFillGray(0.45)
        canvas.drawCentredString(
            PAGE_WIDTH / 2,
            layout.margin_bottom - 10 if layout.margin_bottom > 14 else 6,
            layout.footer_remark[:160],
        )
        canvas.restoreState()


def stamp_watermark(canvas, text: str) -> None:
    """Stamp a document across the page — DUPLICATE, CANCELLED, and so on.

    Drawn light and behind nothing: it is applied after the content, so it has
    to stay readable without obscuring a figure someone needs to read. An
    auditor must be able to tell a reprint from the original at a glance, and
    a cancelled bill from a live one.
    """
    if not text:
        return
    canvas.saveState()
    canvas.setFont("Helvetica-Bold", 64)
    # Light grey rather than a colour: this survives a monochrome laser
    # printer, which is what the counter actually has.
    canvas.setFillGray(0.85)
    canvas.translate(PAGE_WIDTH / 2, PAGE_HEIGHT / 2)
    canvas.rotate(45)
    canvas.drawCentredString(0, 0, text.upper()[:24])
    canvas.restoreState()


def merge_pdfs(documents: Sequence[bytes]) -> bytes:
    """Bind finished PDFs into one file, in the order given.

    Used for the records bundle, where a patient's whole admission is handed
    over as a single document. Empty inputs are skipped rather than raising:
    a bundle missing one optional form is still worth producing.
    """
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    pages = 0
    for document in documents:
        if not document:
            continue
        try:
            reader = PdfReader(io.BytesIO(document))
        except Exception:
            logger.warning("merge_skipped_unreadable_pdf")
            continue
        for page in reader.pages:
            writer.add_page(page)
            pages += 1

    if pages == 0:
        raise ValueError("There was nothing to bundle.")

    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
