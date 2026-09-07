"""Text extraction from uploaded reports.

Strategy, in order:
  PDF  -> read the embedded text layer (fast, exact). If the page yields too
          little text it is a scan, so rasterise and OCR it.
  Image-> preprocess (greyscale, autocontrast, upscale small scans) and OCR.

Every optional dependency is imported defensively and probed at runtime. A
deployment without Tesseract still accepts uploads and stores files; it simply
reports that OCR is unavailable instead of crashing. `extraction_capabilities()`
lets the API tell the front end what this node can actually do.
"""
import io
import shutil
from dataclasses import dataclass
from typing import List, Optional

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# --- optional dependencies -------------------------------------------------
try:
    from pypdf import PdfReader  # type: ignore
    _HAS_PYPDF = True
except ImportError:  # pragma: no cover - depends on deployment image
    PdfReader = None  # type: ignore
    _HAS_PYPDF = False

try:
    from PIL import Image, ImageOps  # type: ignore
    _HAS_PIL = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    ImageOps = None  # type: ignore
    _HAS_PIL = False

try:
    import pytesseract  # type: ignore
    _HAS_PYTESSERACT = True
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore
    _HAS_PYTESSERACT = False

try:
    from pdf2image import convert_from_bytes  # type: ignore
    _HAS_PDF2IMAGE = True
except ImportError:  # pragma: no cover
    convert_from_bytes = None  # type: ignore
    _HAS_PDF2IMAGE = False


def tesseract_available() -> bool:
    return _HAS_PYTESSERACT and _HAS_PIL and shutil.which("tesseract") is not None


def poppler_available() -> bool:
    return _HAS_PDF2IMAGE and shutil.which("pdftoppm") is not None


def extraction_capabilities() -> dict:
    return {
        "pdf_text": _HAS_PYPDF,
        "ocr_images": tesseract_available(),
        "ocr_scanned_pdf": tesseract_available() and poppler_available(),
        "languages": settings.OCR_LANGUAGES,
    }


@dataclass
class ExtractionResult:
    text: str
    method: str                      # pdf_text | ocr | pdf_text+ocr | none
    page_count: Optional[int] = None
    warning: Optional[str] = None

    @property
    def ok(self) -> bool:
        return bool(self.text.strip())


# Below this many characters, a PDF page is treated as a scan rather than text.
_MIN_CHARS_PER_PAGE = 120


def _ocr_image(image) -> str:
    """OCR one PIL image with light preprocessing."""
    prepared = ImageOps.grayscale(image)
    prepared = ImageOps.autocontrast(prepared)
    # Tesseract struggles below ~300 DPI; upscale small scans.
    if prepared.width < 1400:
        ratio = 1400 / float(prepared.width)
        prepared = prepared.resize(
            (1400, max(1, int(prepared.height * ratio))), Image.LANCZOS
        )
    # PSM 6: assume a uniform block of text, which suits tabular lab reports.
    return pytesseract.image_to_string(
        prepared, lang=settings.OCR_LANGUAGES, config="--psm 6"
    )


def extract_from_pdf(data: bytes) -> ExtractionResult:
    if not _HAS_PYPDF:
        return ExtractionResult("", "none", warning="PDF support (pypdf) is not installed.")

    pages: List[str] = []
    page_count = 0
    try:
        reader = PdfReader(io.BytesIO(data))
        page_count = len(reader.pages)
        for page in reader.pages:
            try:
                pages.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - a damaged page must not kill the upload
                pages.append("")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdf_read_failed", extra={"error": repr(exc)})
        return ExtractionResult("", "none", warning=f"Could not read the PDF: {exc}")

    text_layer = "\n".join(pages).strip()
    average = len(text_layer) / page_count if page_count else 0

    if average >= _MIN_CHARS_PER_PAGE:
        return ExtractionResult(text_layer, "pdf_text", page_count)

    # Sparse text layer: this is a scan.
    if not (tesseract_available() and poppler_available()):
        warning = (
            "This PDF appears to be a scan and OCR is not available on this server. "
            "The file is stored, but no text could be read from it."
        )
        return ExtractionResult(text_layer, "pdf_text" if text_layer else "none", page_count, warning)

    try:
        images = convert_from_bytes(
            data, dpi=settings.OCR_DPI, fmt="png",
            first_page=1, last_page=settings.OCR_MAX_PAGES,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("pdf_rasterise_failed", extra={"error": repr(exc)})
        return ExtractionResult(text_layer, "pdf_text", page_count, f"Could not rasterise: {exc}")

    ocr_pages = []
    for image in images:
        try:
            ocr_pages.append(_ocr_image(image))
        except Exception as exc:  # noqa: BLE001
            logger.warning("ocr_page_failed", extra={"error": repr(exc)})
    ocr_text = "\n".join(ocr_pages).strip()

    combined = "\n".join(part for part in (text_layer, ocr_text) if part).strip()
    warning = None
    if page_count > settings.OCR_MAX_PAGES:
        warning = (
            f"Only the first {settings.OCR_MAX_PAGES} of {page_count} pages were "
            "read by OCR."
        )
    method = "pdf_text+ocr" if text_layer and ocr_text else ("ocr" if ocr_text else "none")
    return ExtractionResult(combined, method, page_count, warning)


def extract_from_image(data: bytes) -> ExtractionResult:
    if not tesseract_available():
        return ExtractionResult(
            "", "none",
            warning="OCR is not available on this server, so the image text could not be read.",
        )
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            text = _ocr_image(image)
        return ExtractionResult(text.strip(), "ocr", 1)
    except Exception as exc:  # noqa: BLE001
        logger.warning("image_ocr_failed", extra={"error": repr(exc)})
        return ExtractionResult("", "none", warning=f"Could not read the image: {exc}")


def extract(data: bytes, content_type: str, filename: str = "") -> ExtractionResult:
    lowered = (content_type or "").lower()
    name = (filename or "").lower()
    if "pdf" in lowered or name.endswith(".pdf"):
        return extract_from_pdf(data)
    if lowered.startswith("image/") or name.endswith(
        (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
    ):
        return extract_from_image(data)
    # Plain text uploads are accepted as-is.
    if lowered.startswith("text/") or name.endswith((".txt", ".csv")):
        try:
            return ExtractionResult(data.decode("utf-8", errors="replace"), "plain_text", 1)
        except Exception:  # noqa: BLE001
            pass
    return ExtractionResult("", "none", warning=f"Unsupported file type: {content_type or name}")
