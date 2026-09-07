"""Upload validation — the boundary where hostile files arrive."""
import pytest

from app.core.uploads import sanitize_filename, sniff, validate_upload

pytestmark = pytest.mark.unit

ALLOWED = {
    "application/pdf", "image/png", "image/jpeg", "image/tiff",
    "image/bmp", "image/webp", "text/plain", "text/csv",
}


def check(data, filename, declared):
    return validate_upload(
        data=data, filename=filename, declared_type=declared,
        allowed_types=ALLOWED, max_bytes=25 * 1024 * 1024,
    )


@pytest.mark.parametrize(
    "data,filename,declared",
    [
        (b"%PDF-1.7\ncontent", "report.pdf", "application/pdf"),
        (b"\x89PNG\r\n\x1a\n\x00", "scan.png", "image/png"),
        (b"\xff\xd8\xff\xe0JFIF", "photo.jpg", "image/jpeg"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image.webp", "image/webp"),
        (b"Hemoglobin 12.5 g/dL", "values.txt", "text/plain"),
    ],
)
def test_genuine_files_accepted(data, filename, declared):
    assert check(data, filename, declared).ok


@pytest.mark.parametrize(
    "data,filename,declared,description",
    [
        (b"MZ\x90\x00\x03", "invoice.pdf", "application/pdf", "executable renamed .pdf"),
        (b"#!/bin/sh\nrm -rf /", "report.pdf", "application/pdf", "shell script"),
        (b"<html><script>alert(1)</script>", "x.png", "image/png", "HTML/XSS payload"),
        (b"PK\x03\x04", "archive.pdf", "application/pdf", "zip renamed .pdf"),
        (b"%PDF-1.7 content", "report.png", "image/png", "extension mismatch"),
        (b"", "empty.pdf", "application/pdf", "empty file"),
    ],
)
def test_hostile_or_mislabelled_files_rejected(data, filename, declared, description):
    result = check(data, filename, declared)
    assert not result.ok, f"{description} was accepted"
    assert result.reason


def test_oversized_file_rejected():
    result = check(b"%PDF-" + b"x" * (26 * 1024 * 1024), "huge.pdf", "application/pdf")
    assert not result.ok
    assert "larger than" in result.reason


def test_content_type_header_is_not_trusted():
    """A truthful declared type cannot rescue a file whose bytes disagree."""
    assert not check(b"MZ\x90\x00", "x.pdf", "application/pdf").ok


@pytest.mark.parametrize(
    "raw",
    ["../../etc/passwd", "..\\..\\windows\\win.ini", "<script>.png", "", "a" * 400],
)
def test_filename_sanitisation_blocks_traversal(raw):
    safe = sanitize_filename(raw)
    assert "/" not in safe and "\\" not in safe
    assert not safe.startswith(".")
    assert 0 < len(safe) <= 200


def test_sniff_identifies_known_formats():
    assert sniff(b"%PDF-1.4") == "application/pdf"
    assert sniff(b"\x89PNG\r\n\x1a\n") == "image/png"
    assert sniff(b"not a known format") is None
