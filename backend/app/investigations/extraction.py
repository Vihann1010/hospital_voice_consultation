"""Text extraction from uploaded reports.

Strategy, in order:
  PDF  -> read the embedded text layer (fast, exact). If the page yields too
          little text it is a scan, so rasterise and OCR it.
  Image-> OCR directly with PaddleOCR.

PaddleOCR replaced Tesseract here: Tesseract had no model of table structure,
so a bordered lab-report table (ruled cells around each row) came back as
scrambled or missing values, and small print regularly dropped decimal
points ("27.2" read as "272" — a wrong lab value, not a typo). PaddleOCR's
detector finds text regions independent of ruling lines, which fixed both.

Every optional dependency is imported defensively and probed at runtime. A
deployment without PaddleOCR still accepts uploads and stores files; it
simply reports that OCR is unavailable instead of crashing.
`extraction_capabilities()` lets the API tell the front end what this node
can actually do.
"""
import io
import re
import shutil
import tempfile
import unicodedata
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
    from PIL import Image  # type: ignore
    _HAS_PIL = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore
    _HAS_PIL = False

try:
    from paddleocr import PaddleOCR  # type: ignore
    _HAS_PADDLEOCR = True
except ImportError:  # pragma: no cover
    PaddleOCR = None  # type: ignore
    _HAS_PADDLEOCR = False

try:
    from pdf2image import convert_from_bytes  # type: ignore
    _HAS_PDF2IMAGE = True
except ImportError:  # pragma: no cover
    convert_from_bytes = None  # type: ignore
    _HAS_PDF2IMAGE = False


def _paddle_lang(languages: str) -> str:
    """Map the Tesseract-style setting (e.g. "eng+hin") to a PaddleOCR model.

    PaddleOCR loads one recognition model per language, unlike Tesseract's
    "+"-joined multi-language mode, so this picks the best single model.
    """
    return "hi" if "hin" in languages else "en"


# Loading the models takes a couple of seconds, so the engine is built once
# and reused. The Dockerfile also warms this at build time so the first
# upload in production isn't the one paying for the cold start.
_engine: Optional["PaddleOCR"] = None


def _get_ocr_engine() -> Optional["PaddleOCR"]:
    global _engine
    if not _HAS_PADDLEOCR:
        return None
    if _engine is None:
        _engine = PaddleOCR(
            use_textline_orientation=True, lang=_paddle_lang(settings.OCR_LANGUAGES)
        )
    return _engine


def ocr_available() -> bool:
    return _HAS_PADDLEOCR and _HAS_PIL


def poppler_available() -> bool:
    return _HAS_PDF2IMAGE and shutil.which("pdftoppm") is not None


def extraction_capabilities() -> dict:
    return {
        "pdf_text": _HAS_PYPDF,
        "ocr_images": ocr_available(),
        "ocr_scanned_pdf": ocr_available() and poppler_available(),
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

    @property
    def legible(self) -> bool:
        """Did this actually come back as readable text?

        Handwriting is the case that matters. Tesseract does not decline to
        read a handwritten prescription; it returns a page of plausible-
        looking rubbish, and everything downstream treats that as content.
        """
        return is_legible(self.text)


# Tuned to be reluctant. Wrongly hiding a real report is worse than showing a
# doubtful one with a caveat, so a page is only called illegible when several
# signals agree.
_MIN_LEGIBLE_CHARS = 40


def is_legible(text: str) -> bool:
    """A rough judgement on whether OCR output is words or noise."""
    stripped = (text or "").strip()
    if len(stripped) < _MIN_LEGIBLE_CHARS:
        return False

    # Letters, combining marks and digits are all content. Marks matter:
    # Devanagari vowels are matras attached to the consonant, and `isalpha`
    # rejects them, which scored readable Hindi below the bar.
    useful = sum(
        1 for ch in stripped
        if unicodedata.category(ch)[0] in ("L", "M", "N")
    )
    # Noise from a handwritten page is mostly punctuation and stray strokes.
    if useful / len(stripped) < 0.55:
        return False

    # Real words are long enough to be words and contain vowels. Tesseract
    # hallucinating over pen strokes produces short consonant clusters —
    # "PosK", "SSC", "PRG" — which clear a naive letters-only test easily.
    # This is the check that separates a scribbled prescription from a
    # printed one.
    latin = [
        token for token in re.split(r"[^A-Za-z]+", stripped)
        if len(token) >= 4 and any(vowel in token.lower() for vowel in "aeiou")
    ]

    # The vowel rule is a Latin-alphabet rule, and applying it to Devanagari
    # rejects every Hindi report — matras are attached to the consonant, so
    # a readable word contains no [aeiou] at all. Non-Latin letter runs are
    # therefore counted on their own terms. Scribble produces neither.
    other_script = [
        token for token in re.split(r"[\sA-Za-z0-9]+", stripped)
        if len(token) >= 3 and any(ch.isalpha() for ch in token)
    ]

    return len(latin) + len(other_script) >= 6


# Below this many characters, a PDF page is treated as a scan rather than text.
_MIN_CHARS_PER_PAGE = 120


def _reconstruct_rows(texts: List[str], boxes) -> str:
    """Turn PaddleOCR's per-box results back into table rows.

    PaddleOCR detects and recognises each word/phrase as an independent box;
    it does not group boxes on the same printed row the way Tesseract's line
    segmentation does. `parsing.py` depends on a row being one line ("name
    value unit range"), so without this every result is split across three
    or four separate lines and the deterministic parser finds nothing to
    read. Boxes are clustered by vertical overlap into rows, then ordered
    left to right within each row — the same layout Tesseract used to hand
    the parser, just derived from PaddleOCR's box coordinates instead.
    """
    if boxes is None or len(boxes) == 0:
        return "\n".join(texts)

    items = sorted(
        ((float(y1), float(y2), float(x1), text) for (x1, y1, x2, y2), text in zip(boxes, texts)),
        key=lambda item: (item[0] + item[1]) / 2,
    )

    rows: List[List[tuple]] = []
    row_y_range: Optional[tuple] = None
    for y1, y2, x1, text in items:
        y_center = (y1 + y2) / 2
        if rows and row_y_range and not (row_y_range[0] <= y_center <= row_y_range[1]):
            row_y_range = None
        if row_y_range is None:
            rows.append([])
            row_y_range = (y1, y2)
        else:
            row_y_range = (min(row_y_range[0], y1), max(row_y_range[1], y2))
        rows[-1].append((x1, text))

    lines = []
    for row in rows:
        row.sort(key=lambda item: item[0])
        lines.append("   ".join(text for _, text in row))
    return "\n".join(lines)


def _ocr_image(image) -> str:
    """OCR one PIL image.

    PaddleOCR's `predict()` takes a file path (or ndarray); a PIL image is
    written to a temp file rather than converted to an array to avoid
    RGB/BGR channel-order bugs. No manual preprocessing here — PaddleOCR's
    own detector/recognizer already expects natural, un-degraded images, and
    hand-tuned greyscale/contrast/sharpen steps that helped Tesseract made no
    measurable difference (or hurt) with this engine.
    """
    engine = _get_ocr_engine()
    with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
        image.convert("RGB").save(tmp.name)
        results = engine.predict(tmp.name)
    pages: List[str] = []
    for page in results:
        pages.append(_reconstruct_rows(page.get("rec_texts") or [], page.get("rec_boxes")))
    return "\n".join(pages)


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
    if not (ocr_available() and poppler_available()):
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
    if not ocr_available():
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


# Control characters that a PDF text layer can carry and Postgres will not
# store. A single NUL byte in an otherwise perfect report aborted the whole
# upload with "invalid byte sequence for encoding UTF8", losing the file. Tabs
# and newlines are kept: they are the column separators this parser relies on.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def scrub(text: str) -> str:
    """Make extracted text safe to store, without changing what it says."""
    return _CONTROL_CHARS.sub(" ", text or "")


def extract(data: bytes, content_type: str, filename: str = "") -> ExtractionResult:
    lowered = (content_type or "").lower()
    name = (filename or "").lower()

    if "pdf" in lowered or name.endswith(".pdf"):
        result = extract_from_pdf(data)
    elif lowered.startswith("image/") or name.endswith(
        (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
    ):
        result = extract_from_image(data)
    elif lowered.startswith("text/") or name.endswith((".txt", ".csv")):
        # Plain text uploads are accepted as-is.
        result = ExtractionResult(data.decode("utf-8", errors="replace"), "plain_text", 1)
    else:
        return ExtractionResult(
            "", "none", warning=f"Unsupported file type: {content_type or name}"
        )

    # Scrubbed once, here, so nothing downstream has to remember to.
    result.text = scrub(result.text)
    return result
