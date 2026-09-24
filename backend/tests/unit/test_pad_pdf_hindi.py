"""The pad prints Hindi, not boxes.

The print layout names a Latin font — Helvetica by default — and Helvetica
has no Devanagari at all, so the pad's Hindi history and Hindi instructions
came out as empty squares. The face is now chosen per line, from the text
itself, so one bilingual pad can carry both.
"""
import pytest

from app.pads.pdf import _has_devanagari, _style

pytestmark = pytest.mark.unit


class _Style:
    def __init__(self, name):
        self.name = name


STYLES = {"body": _Style("body"), "body_hi": _Style("body_hi"),
          "bullet": _Style("bullet"), "bullet_hi": _Style("bullet_hi")}


@pytest.mark.parametrize("text,hindi", [
    ("तीन दिन पहले दांत में दर्द", True),
    ("Amoxicillin 500 — 1 capsule", False),
    ("Amoxicillin 500 — 1 कैप्सूल, दिन में तीन बार", True),   # mixed: must shape
    ("", False),
])
def test_a_line_is_hindi_when_it_carries_devanagari(text, hindi):
    assert _has_devanagari(text) is hindi


def test_a_hindi_line_is_drawn_in_the_hindi_face():
    assert _style(STYLES, "body", "गुनगुने पानी से कुल्ला करें").name == "body_hi"
    assert _style(STYLES, "bullet", "Take after food").name == "bullet"


def test_a_server_without_a_devanagari_font_still_prints():
    """No Hindi twin registered: fall back rather than raise mid-print."""
    assert _style({"body": _Style("body")}, "body", "दर्द").name == "body"
