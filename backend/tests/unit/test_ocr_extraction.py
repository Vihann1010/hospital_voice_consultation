"""Extraction switched from Tesseract to PaddleOCR: Tesseract had no model of
table structure and scrambled or dropped rows on a bordered lab-report
table, and separately dropped decimal points in small print ("27.2" read
as "272"). PaddleOCR's detector fixed both on real hospital report scans
(verified manually against production images, not something a unit test
can check without the model weights).

That switch introduced a real regression of its own: PaddleOCR recognises
each word/phrase as an independent box and does not group boxes on the same
printed row the way Tesseract's line segmentation did. `parsing.py` expects
one table row per line ("name value unit range"); without reconstructing
rows from box coordinates, every result was split across three or four
lines and the deterministic parser found nothing to read (caught by running
the real report images end to end through a built Docker image, not by a
unit test — these tests cover the fix so it can't regress silently again).
"""
import pytest
from PIL import Image

from app.investigations import extraction

pytestmark = pytest.mark.unit


class _FakeEngine:
    def __init__(self, pages):
        self._pages = pages
        self.received_path = None

    def predict(self, path):
        self.received_path = path
        return self._pages


def test_boxes_on_the_same_row_are_joined_into_one_line():
    # A row like "Hemoglobin (Hb)   12.5   Low 13.0 - 17.0   g/dL", each cell
    # its own box, all roughly at the same height.
    texts = ["Hemoglobin (Hb)", "12.5", "Low 13.0 - 17.0", "g/dL"]
    boxes = [
        (10, 100, 200, 130),
        (220, 102, 260, 128),
        (280, 100, 420, 130),
        (440, 101, 480, 129),
    ]
    assert extraction._reconstruct_rows(texts, boxes) == (
        "Hemoglobin (Hb)   12.5   Low 13.0 - 17.0   g/dL"
    )


def test_boxes_on_different_rows_stay_on_separate_lines():
    texts = ["HEMOGLOBIN", "Hemoglobin (Hb)", "12.5"]
    boxes = [
        (10, 50, 150, 75),     # section heading, its own row
        (10, 100, 200, 130),   # next row, left cell
        (220, 102, 260, 128),  # next row, right cell — overlaps the row above it
    ]
    assert extraction._reconstruct_rows(texts, boxes) == (
        "HEMOGLOBIN\nHemoglobin (Hb)   12.5"
    )


def test_row_order_follows_left_to_right_regardless_of_detection_order():
    texts = ["g/dL", "Hemoglobin (Hb)", "12.5"]
    boxes = [(440, 101, 480, 129), (10, 100, 200, 130), (220, 102, 260, 128)]
    assert extraction._reconstruct_rows(texts, boxes) == "Hemoglobin (Hb)   12.5   g/dL"


def test_reconstruct_rows_falls_back_to_plain_join_without_boxes():
    assert extraction._reconstruct_rows(["a", "b"], None) == "a\nb"
    assert extraction._reconstruct_rows(["a", "b"], []) == "a\nb"


def test_ocr_image_reconstructs_rows_from_all_pages(monkeypatch):
    fake = _FakeEngine([
        {
            "rec_texts": ["Hemoglobin", "12.5"],
            "rec_boxes": [(10, 100, 200, 130), (220, 102, 260, 128)],
        },
        {
            "rec_texts": ["Page 2"],
            "rec_boxes": [(10, 10, 100, 30)],
        },
    ])
    monkeypatch.setattr(extraction, "_get_ocr_engine", lambda: fake)

    text = extraction._ocr_image(Image.new("RGB", (10, 10), color="white"))

    assert text == "Hemoglobin   12.5\nPage 2"
    assert fake.received_path is not None


def test_ocr_available_reflects_dependency_presence(monkeypatch):
    monkeypatch.setattr(extraction, "_HAS_PADDLEOCR", True)
    monkeypatch.setattr(extraction, "_HAS_PIL", True)
    assert extraction.ocr_available() is True

    monkeypatch.setattr(extraction, "_HAS_PADDLEOCR", False)
    assert extraction.ocr_available() is False


@pytest.mark.parametrize("languages,expected", [("eng", "en"), ("hin", "hi"), ("eng+hin", "hi")])
def test_paddle_lang_maps_tesseract_style_setting(languages, expected):
    assert extraction._paddle_lang(languages) == expected
