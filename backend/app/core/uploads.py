"""Upload validation.

The browser-supplied Content-Type and file extension are both attacker
controlled, so neither is trusted on its own: the file's leading bytes must
match a permitted format. This is what stops a renamed executable or an HTML
file with an XSS payload from being stored and later served back.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

# Magic-byte signatures for the formats a hospital actually uploads.
SIGNATURES: Dict[str, Tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/bmp": (b"BM",),
    "image/tiff": (b"II*\x00", b"MM\x00*"),
    "image/webp": (b"RIFF",),          # plus a WEBP tag at offset 8
}

EXTENSION_TO_TYPE: Dict[str, str] = {
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".bmp": "image/bmp",
    ".tif": "image/tiff", ".tiff": "image/tiff", ".webp": "image/webp",
    ".txt": "text/plain", ".csv": "text/csv",
}

TEXT_TYPES: Set[str] = {"text/plain", "text/csv"}


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    detected_type: Optional[str] = None
    reason: Optional[str] = None


def sniff(data: bytes) -> Optional[str]:
    """Identify a file from its leading bytes, or None if unrecognised."""
    if not data:
        return None
    for media_type, signatures in SIGNATURES.items():
        for signature in signatures:
            if data.startswith(signature):
                if media_type == "image/webp":
                    if len(data) >= 12 and data[8:12] == b"WEBP":
                        return media_type
                    continue
                return media_type
    return None


def looks_like_text(data: bytes) -> bool:
    """Heuristic for plain text: decodable and free of control bytes."""
    sample = data[:4096]
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
    except UnicodeDecodeError:
        try:
            sample.decode("latin-1")
        except UnicodeDecodeError:
            return False
    return True


def sanitize_filename(name: str, fallback: str = "upload") -> str:
    """Strip directory components and dangerous characters."""
    base = Path(name or "").name
    cleaned = "".join(
        character for character in base
        if character.isalnum() or character in " ._-()"
    ).strip()
    cleaned = cleaned.lstrip(".") or fallback
    return cleaned[:200]


def validate_upload(
    *,
    data: bytes,
    filename: str,
    declared_type: str,
    allowed_types: Set[str],
    max_bytes: int,
) -> ValidationResult:
    if not data:
        return ValidationResult(False, reason="The uploaded file is empty.")
    if len(data) > max_bytes:
        return ValidationResult(
            False,
            reason=f"File is larger than the {max_bytes // (1024 * 1024)} MB limit.",
        )

    suffix = Path(filename or "").suffix.lower()
    detected = sniff(data)

    if detected is None:
        # Text uploads have no signature, so fall back to a content heuristic —
        # but only when both the extension and declared type say text.
        expected = EXTENSION_TO_TYPE.get(suffix)
        if expected in TEXT_TYPES and declared_type in TEXT_TYPES and looks_like_text(data):
            detected = expected
        else:
            return ValidationResult(
                False,
                reason="The file content does not match any accepted format "
                       "(PDF, PNG, JPEG, TIFF, BMP, WebP or plain text).",
            )

    if detected not in allowed_types:
        return ValidationResult(
            False, detected_type=detected,
            reason=f"Files of type {detected} are not accepted here.",
        )

    # A mismatch between the real format and the extension is suspicious enough
    # to reject: it is the signature of a disguised upload.
    expected_from_extension = EXTENSION_TO_TYPE.get(suffix)
    if expected_from_extension and expected_from_extension != detected:
        interchangeable = {"image/jpeg", "image/tiff"}
        if not (expected_from_extension in interchangeable and detected in interchangeable):
            return ValidationResult(
                False, detected_type=detected,
                reason=f"This file is actually {detected} but is named '{suffix}'. "
                       "Rename it correctly and upload again.",
            )
    return ValidationResult(True, detected_type=detected)
